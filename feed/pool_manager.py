"""
pool_manager.py — one pool of extractors per filter set.

Model (Phase 2): every distinct search querystring = one pool. Clients that pick
the same filters (same normalized querystring) share the same pool; different
filters → dedicated pool. The pool is created on the first client and shuts down
when the last client of that set disconnects.
"""

import asyncio
from os import getenv
from urllib.parse import parse_qsl, urlencode

from fastapi import WebSocket

from extractor import ExtractorFactory

# Cap on the number of simultaneous pools (one pool = one distinct filter set,
# with its own extractors on paid proxies). Anti-DoS defense. See VLF-01.
MAX_POOLS = int(getenv('FEED_MAX_POOLS', '300'))


def normalize_query(query: str) -> str:
  """Canonical key for a filter set: parameters sorted, so two clients with the
  same filters (even in a different order) end up in the same pool."""
  pairs = parse_qsl(query, keep_blank_values=False)
  pairs.sort()
  return urlencode(pairs)


class _Pool:
  """A pool of extractors dedicated to a querystring, with its own clients."""

  def __init__(self, url: str):
    self.url = url
    self.clients: list[WebSocket] = []
    self.client_connected = asyncio.Event()
    self.factory = ExtractorFactory(self._broadcast, self.client_connected)
    self._tasks: list[asyncio.Task] = []

  async def _broadcast(self, msg: str):
    for c in self.clients[:]:
      try:
        await c.send_text(msg)
      except Exception:
        continue

  def start(self):
    self._tasks = [
      asyncio.create_task(self.factory.fetch_data_loop(self.url)),
      asyncio.create_task(self.factory.get_cookies_loop()),
      asyncio.create_task(self.factory.get_cookies_loop()),
      asyncio.create_task(self.factory.get_cookies_loop()),
    ]

  async def stop(self):
    for t in self._tasks:
      t.cancel()
    self._tasks = []
    # Closes the sessions of the extractors left in the pool.
    for ext in self.factory.extractors[:]:
      try:
        await ext.session.close()
      except Exception:
        pass
    self.factory.extractors.clear()


class PoolManager:
  """Creates/destroys pools based on the connected clients and their filters."""

  def __init__(self, default_url: str, base_url: str):
    # URL used when the client passes no filters (default feed).
    self.default_url = default_url
    # Base to which the filter querystring is attached.
    self.base_url = base_url
    self.pools: dict[str, _Pool] = {}
    self._lock = asyncio.Lock()

  def _url_for(self, key: str) -> str:
    return f'{self.base_url}?{key}' if key else self.default_url

  async def add_client(self, query: str, ws: WebSocket) -> str | None:
    """Registers a client in the pool for its filter set. Returns the key, or
    None if the pool cap has been reached (new set rejected)."""
    key = normalize_query(query)
    async with self._lock:
      pool = self.pools.get(key)
      if pool is None:
        if len(self.pools) >= MAX_POOLS:
          print(f'pool REJECTED (cap {MAX_POOLS} reached): {key or "(default)"}')
          return None
        pool = _Pool(self._url_for(key))
        self.pools[key] = pool
        pool.start()
        print(f'pool created for filters: {key or "(default)"}')
      pool.clients.append(ws)
      pool.client_connected.set()
    return key

  async def remove_client(self, key: str, ws: WebSocket):
    async with self._lock:
      pool = self.pools.get(key)
      if not pool:
        return
      if ws in pool.clients:
        pool.clients.remove(ws)
      if not pool.clients:
        pool.client_connected.clear()
        await pool.stop()
        del self.pools[key]
        print(f'pool shut down for filters: {key or "(default)"}')

  async def shutdown(self):
    async with self._lock:
      for pool in list(self.pools.values()):
        await pool.stop()
      self.pools.clear()

  def stats(self) -> dict:
    return {
      'pools': len(self.pools),
      'clients': sum(len(p.clients) for p in self.pools.values()),
    }

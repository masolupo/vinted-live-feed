"""
vinted_meta.py — source of the metadata for the UI filters.

Strategy ("hybrid" approach):
  - Categories: there is NO API endpoint on Vinted (404). The tree is
    serialized as `catalogTree` in the home page HTML. We extract it and save
    it to `data/categories.json` (static base, always works); a background job
    regenerates it every so often and updates the file.
  - Brands / colors / sizes / conditions: real API endpoints, fetched live and
    cached with a TTL.

All requests go through the proxy (env PROXY), like the feed extractors.
"""

import asyncio
import json
import time
from os import getenv
from pathlib import Path

from curl_cffi.requests import AsyncSession

BASE = 'https://vinted.it'
DATA_DIR = Path(__file__).parent / 'data'
CATEGORIES_FILE = DATA_DIR / 'categories.json'

# How often the job regenerates the categories (seconds).
CATEGORIES_REFRESH_S = 24 * 60 * 60
# Cache TTL for the near-static lists (colors/sizes/conditions).
STATIC_TTL_S = 6 * 60 * 60
# Cache TTL for the brand search (per query).
BRANDS_TTL_S = 5 * 60


def _proxy() -> str:
  p = getenv('PROXY')
  if not p:
    raise ValueError('PROXY env not found')
  return p


def _extract_array(text: str, key: str) -> str | None:
  """Extracts the array value of `"key":[ ... ]` from `text` (already unescaped),
  with bracket-matching that respects strings."""
  marker = f'"{key}":'
  k = text.find(marker)
  if k == -1:
    return None
  i = text.find('[', k)
  if i == -1:
    return None

  depth = 0
  instr = False
  esc = False
  for j in range(i, len(text)):
    c = text[j]
    if instr:
      if esc:
        esc = False
      elif c == '\\':
        esc = True
      elif c == '"':
        instr = False
    else:
      if c == '"':
        instr = True
      elif c == '[':
        depth += 1
      elif c == ']':
        depth -= 1
        if depth == 0:
          return text[i:j + 1]
  return None


def _slim_node(node: dict) -> dict:
  """Keeps only the fields the UI needs, recursively."""
  return {
    'id': node.get('id'),
    'title': node.get('title'),
    'code': node.get('code'),
    'catalogs': [_slim_node(c) for c in (node.get('catalogs') or [])],
  }


class VintedMeta:
  """Client for the filter metadata. Reuses a session (with cookie bootstrap)
  and an in-memory cache. The session is recreated on error."""

  def __init__(self):
    self._session: AsyncSession | None = None
    self._sess_lock = asyncio.Lock()
    self._cache: dict[str, tuple[float, object]] = {}
    self._cache_lock = asyncio.Lock()
    self.categories: list[dict] = []

  # ── session ─────────────────────────────────────────────────────────────

  async def _get_session(self) -> AsyncSession:
    async with self._sess_lock:
      if self._session is None:
        s = AsyncSession(impersonate='chrome', proxy=_proxy())
        await s.get(BASE, timeout=25)  # bootstrap anonymous cookies
        self._session = s
      return self._session

  async def _reset_session(self):
    async with self._sess_lock:
      if self._session is not None:
        try:
          await self._session.close()
        except Exception:
          pass
        self._session = None

  async def _api_json(self, path: str, tries: int = 4):
    last: Exception | None = None
    for attempt in range(tries):
      try:
        s = await self._get_session()
        r = await s.get(BASE + path, timeout=25)
        if r.status_code == 200:
          return r.json()
        last = Exception(f'status {r.status_code} on {path}')
      except Exception as e:
        last = e
        await self._reset_session()
      await asyncio.sleep(1)
    raise last or Exception('request failed')

  # ── cache ───────────────────────────────────────────────────────────────

  async def _cached(self, key: str, ttl: float, producer):
    async with self._cache_lock:
      hit = self._cache.get(key)
      if hit and hit[0] > time.monotonic():
        return hit[1]
    value = await producer()
    async with self._cache_lock:
      self._cache[key] = (time.monotonic() + ttl, value)
    return value

  # ── categories (HTML → catalogTree) ───────────────────────────────────────

  async def fetch_categories_live(self) -> list[dict]:
    """Extracts the catalogTree from the home page HTML and returns it slimmed down."""
    s = AsyncSession(impersonate='chrome', proxy=_proxy())
    try:
      r = await s.get(BASE, timeout=25)
      html = r.text
      txt = html.replace('\\"', '"').replace('\\\\', '\\')
      arr = _extract_array(txt, 'catalogTree')
      if not arr:
        raise ValueError('catalogTree not found in the HTML')
      tree = json.loads(arr)
      return [_slim_node(n) for n in tree]
    finally:
      try:
        await s.close()
      except Exception:
        pass

  def load_categories_from_file(self) -> list[dict]:
    """Loads the categories from the static file (base that always works)."""
    if CATEGORIES_FILE.exists():
      self.categories = json.loads(CATEGORIES_FILE.read_text())
    else:
      self.categories = []
    return self.categories

  def _save_categories(self, cats: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_FILE.write_text(json.dumps(cats, ensure_ascii=False, indent=2))

  async def refresh_categories(self) -> bool:
    """Regenerates the categories from Vinted and updates file + memory.
    Returns False on failure (keeping the old ones)."""
    try:
      cats = await self.fetch_categories_live()
      if cats:
        self.categories = cats
        self._save_categories(cats)
        return True
    except Exception as e:
      print(f'refresh_categories failed: {e}')
    return False

  async def categories_refresh_loop(self):
    """Background job: regenerates the categories periodically."""
    while True:
      await self.refresh_categories()
      await asyncio.sleep(CATEGORIES_REFRESH_S)

  # ── filters with real API endpoints ───────────────────────────────────────

  async def get_colors(self):
    return await self._cached(
      'colors', STATIC_TTL_S,
      lambda: self._api_json('/api/v2/colors'),
    )

  async def get_sizes(self):
    return await self._cached(
      'sizes', STATIC_TTL_S,
      lambda: self._api_json('/api/v2/size_groups'),
    )

  async def get_conditions(self):
    return await self._cached(
      'conditions', STATIC_TTL_S,
      lambda: self._api_json('/api/v2/statuses'),
    )

  async def search_brands(self, q: str):
    key = f'brands:{q.strip().lower()}'
    path = f'/api/v2/brands?keyword={q}' if q else '/api/v2/brands'
    return await self._cached(key, BRANDS_TTL_S, lambda: self._api_json(path))

  async def close(self):
    await self._reset_session()

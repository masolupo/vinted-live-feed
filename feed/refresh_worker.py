"""
refresh_worker.py — keeps Vinted sessions alive without spamming requests.

Unlike a fixed-interval keep-alive, it renews a session ONLY when its
refresh_token is about to expire (within VINTED_REFRESH_BEFORE_DAYS, default
2 days). Each refresh regenerates a 7-day refresh_token → in practice ~1 call
every ~5 days per user, even when they are offline.

The fresh access_token used for a purchase is fetched on-demand at buy time,
not here.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from os import getenv

import db
import proxy_pool
import session_refresh
import vinted_store

# How often to CHECK (a lightweight query). Must be frequent enough to catch the
# access refresh window (online), but the actual call to Vinted only fires for
# sessions that are genuinely due. Default 5 min.
CHECK_INTERVAL = int(getenv('VINTED_REFRESH_CHECK_INTERVAL', '300'))
# How far BEFORE the refresh_token expiry to renew (offline keepalive).
RENEW_BEFORE = timedelta(days=int(getenv('VINTED_REFRESH_BEFORE_DAYS', '2')))
# How recent the last heartbeat must be to consider the user "online".
ACTIVE_WINDOW = timedelta(seconds=int(getenv('VINTED_ACTIVE_WINDOW_SEC', '600')))
# VLF-07: retention for buy_debug records (raw payment responses). 0 = never.
BUY_DEBUG_DAYS = int(getenv('VINTED_BUY_DEBUG_DAYS', '30'))
# How many ticks between buy_debug purges (no need to run every cycle).
_PURGE_EVERY_TICKS = 12
_tick = 0


def _still_due(row) -> bool:
  """Under lock: does the session still need renewing? (another path may have
  just renewed it between the due-query and acquiring the lock)."""
  now = datetime.now(timezone.utc)
  refresh_due = row['refresh_expires_at'] is not None and row['refresh_expires_at'] <= now + RENEW_BEFORE
  online = row['last_active_at'] is not None and row['last_active_at'] >= now - ACTIVE_WINDOW
  online_due = online and row['next_refresh_at'] is not None and row['next_refresh_at'] <= now
  return refresh_due or online_due


async def _refresh_one(conn, row) -> None:
  user_id = row['user_id']
  proxy_url = proxy_pool.build_url(row['zone'], row['ip']) if row['zone'] else ''
  outcome = await session_refresh.locked_refresh(conn, user_id, proxy_url, _still_due)
  print(f'refresh: user {user_id} → {outcome}')


async def _purge_buy_debug(pool) -> None:
  """VLF-07: periodically clears out expired buy-debug records."""
  if BUY_DEBUG_DAYS <= 0:
    return
  try:
    async with pool.acquire() as conn:
      n = await vinted_store.purge_buy_debug(conn, BUY_DEBUG_DAYS)
    if n:
      print(f'refresh: buy_debug purge → {n} records removed (>{BUY_DEBUG_DAYS}d)')
  except Exception as e:
    print(f'refresh: buy_debug purge error: {type(e).__name__}: {str(e)[:120]}')


async def _cycle(pool) -> None:
  global _tick
  _tick += 1
  if _tick % _PURGE_EVERY_TICKS == 1:
    await _purge_buy_debug(pool)
  async with pool.acquire() as conn:
    rows = await vinted_store.due_for_refresh(conn, RENEW_BEFORE, ACTIVE_WINDOW)
  if not rows:
    return
  print(f'refresh: {len(rows)} sessions to renew')
  for row in rows:
    async with pool.acquire() as conn:
      try:
        await _refresh_one(conn, row)
      except Exception as e:
        print(f'refresh: error on {row["user_id"]}: {type(e).__name__}: {str(e)[:160]}')


async def refresh_loop() -> None:
  """Main loop. If the DB pool is absent, it stays idle without doing any harm."""
  if db.get_pool() is None:
    print('refresh: DB pool absent → worker disabled')
    return
  print(f'refresh: worker active (tick {CHECK_INTERVAL}s; keepalive {RENEW_BEFORE.days}d '
        f'before expiry; fresh access if online within {int(ACTIVE_WINDOW.total_seconds() // 60)}min)')
  while True:
    pool = db.get_pool()
    if pool is not None:
      try:
        await _cycle(pool)
      except Exception as e:
        print(f'refresh: error in cycle: {type(e).__name__}: {str(e)[:160]}')
    await asyncio.sleep(CHECK_INTERVAL)

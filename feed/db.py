"""
db.py — shared asyncpg pool to the Supabase Postgres (DATABASE_URL).

Used by the features that read/write the DB (proxy_pool, vinted_sessions).
If DATABASE_URL is not configured, the pool stays None and the related features
stay inactive without breaking the rest of the feed service.
"""

from os import getenv

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool | None:
  global _pool
  dsn = getenv('DATABASE_URL')
  if not dsn:
    print('db: DATABASE_URL not configured → pool disabled')
    return None
  # max_size a bit generous: refreshes hold the connection (+ advisory lock)
  # during the network call to Vinted.
  _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10, timeout=15)
  print('db: asyncpg pool ready')
  return _pool


def get_pool() -> asyncpg.Pool | None:
  return _pool


async def close_pool():
  global _pool
  if _pool is not None:
    await _pool.close()
    _pool = None

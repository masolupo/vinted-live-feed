"""
proxy_pool.py — assignment of the dedicated IPs (BrightData) to users.

Each user has 1 fixed Italian IP (proxy_pool table). The zone password and the
URL parts live in env; the DB keeps only zone+IP+status.
"""

from os import getenv

import asyncpg


def build_url(zone: str, ip: str) -> str:
  """Builds the full proxy URL with the pinned IP (-ip-).
  Reads the parts from env at runtime (robust with respect to import order)."""
  host   = getenv('BRD_PROXY_HOST', 'brd.superproxy.io:33335')
  prefix = getenv('BRD_PROXY_USER_PREFIX', '')
  pwd    = getenv('BRD_ZONE_PASSWORD', '')
  return f'http://{prefix}-zone-{zone}-ip-{ip}:{pwd}@{host}'


async def assign(conn: asyncpg.Connection, user_id: str) -> dict | None:
  """
  Returns the user's proxy, assigning a free one if they don't already have one.
  Returns {'id', 'zone', 'ip', 'url'} or None if the pool is exhausted.
  """
  # Already assigned? reuse the same IP.
  row = await conn.fetchrow(
    "select id, zone, ip from public.proxy_pool "
    "where assigned_user_id = $1 and status = 'assigned'",
    user_id,
  )
  if row is None:
    # Grab a free IP (row lock, skip the ones already taken by others).
    row = await conn.fetchrow(
      "update public.proxy_pool set status = 'assigned', "
      "  assigned_user_id = $1, assigned_at = now() "
      "where id = ("
      "  select id from public.proxy_pool where status = 'free' "
      "  order by created_at limit 1 for update skip locked"
      ") returning id, zone, ip",
      user_id,
    )
  if row is None:
    return None
  return {
    'id':   row['id'],
    'zone': row['zone'],
    'ip':   row['ip'],
    'url':  build_url(row['zone'], row['ip']),
  }


async def release(conn: asyncpg.Connection, user_id: str):
  """Frees the user's proxy (back to 'free'). Does not touch the 'burned' ones."""
  await conn.execute(
    "update public.proxy_pool set status = 'free', assigned_user_id = null, "
    "  assigned_at = null where assigned_user_id = $1 and status = 'assigned'",
    user_id,
  )


async def burn(conn: asyncpg.Connection, proxy_id) -> None:
  """Marks an IP as burned (rejected by Vinted): it will no longer be assigned."""
  await conn.execute(
    "update public.proxy_pool set status = 'burned' where id = $1",
    proxy_id,
  )

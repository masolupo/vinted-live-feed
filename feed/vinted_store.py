"""
vinted_store.py — persistence of a user's Vinted session.

Saves/reads the vinted_sessions row. The tokens (access/refresh/cookies) are
encrypted with token_crypto before touching the DB.
"""

import json
import random
from datetime import datetime, timedelta, timezone
from os import getenv

import asyncpg

import token_crypto

# Durations declared by Vinted (see vba/VINTED_SESSION.md).
ACCESS_TTL  = timedelta(hours=2)
REFRESH_TTL = timedelta(days=7)

# When the user is online, the access token must be renewed BEFORE 2h, but at a
# randomized time (not a fixed cadence) so as not to arouse the anti-bot: the
# refresh falls between MIN and MAX minutes before the access token expires.
ACCESS_MIN_BEFORE = timedelta(minutes=int(getenv('VINTED_ACCESS_MIN_BEFORE_MIN', '20')))
ACCESS_MAX_BEFORE = timedelta(minutes=int(getenv('VINTED_ACCESS_MAX_BEFORE_MIN', '60')))


def _now() -> datetime:
  return datetime.now(timezone.utc)


def _next_refresh_at(now: datetime) -> datetime:
  """(Jittered) time of the next access refresh: expiry − random(min,max)."""
  span = (ACCESS_MAX_BEFORE - ACCESS_MIN_BEFORE).total_seconds()
  before = ACCESS_MIN_BEFORE + timedelta(seconds=random.uniform(0, max(span, 0)))
  return now + ACCESS_TTL - before


async def save(conn: asyncpg.Connection, user_id: str, vs, proxy_id) -> None:
  """Upsert the session after a successful login (fresh tokens)."""
  now = _now()
  await conn.execute(
    """
    insert into public.vinted_sessions
      (user_id, vinted_user_id, access_token, refresh_token, cookies, csrf,
       proxy_id, status, access_expires_at, refresh_expires_at,
       last_refresh_at, last_active_at, next_refresh_at, updated_at)
    values ($1,$2,$3,$4,$5,$6,$7,'active',$8,$9,$10,$10,$11,$10)
    on conflict (user_id) do update set
      vinted_user_id     = excluded.vinted_user_id,
      access_token       = excluded.access_token,
      refresh_token      = excluded.refresh_token,
      cookies            = excluded.cookies,
      csrf               = excluded.csrf,
      proxy_id           = excluded.proxy_id,
      status             = 'active',
      access_expires_at  = excluded.access_expires_at,
      refresh_expires_at = excluded.refresh_expires_at,
      last_refresh_at    = excluded.last_refresh_at,
      last_active_at     = excluded.last_active_at,
      next_refresh_at    = excluded.next_refresh_at,
      updated_at         = excluded.updated_at
    """,
    user_id,
    vs.vinted_user_id,
    token_crypto.encrypt(vs.access_token),
    token_crypto.encrypt(vs.refresh_token),
    token_crypto.encrypt(json.dumps(vs.cookies)),
    vs.csrf,
    proxy_id,
    now + ACCESS_TTL,
    now + REFRESH_TTL,
    now,
    _next_refresh_at(now),
  )


async def get_status(conn: asyncpg.Connection, user_id: str) -> str:
  """'connected' | 'expired' | 'none' for the UI."""
  row = await conn.fetchrow(
    'select status from public.vinted_sessions where user_id = $1',
    user_id,
  )
  if row is None:
    return 'none'
  return 'connected' if row['status'] == 'active' else 'expired'


async def delete(conn: asyncpg.Connection, user_id: str) -> None:
  await conn.execute(
    'delete from public.vinted_sessions where user_id = $1',
    user_id,
  )


async def load_session(conn: asyncpg.Connection, user_id: str) -> dict | None:
  """Full decrypted session (for the purchase). None if it doesn't exist."""
  row = await conn.fetchrow(
    """
    select s.status, s.access_token, s.refresh_token, s.cookies, s.csrf,
           s.access_expires_at, s.refresh_expires_at, s.vinted_user_id,
           p.zone, p.ip
    from public.vinted_sessions s
    left join public.proxy_pool p on p.id = s.proxy_id
    where s.user_id = $1
    """,
    user_id,
  )
  if row is None:
    return None
  return {
    'status':             row['status'],
    'access_token':       token_crypto.decrypt(row['access_token']) if row['access_token'] else '',
    'refresh_token':      token_crypto.decrypt(row['refresh_token']) if row['refresh_token'] else '',
    'cookies':            json.loads(token_crypto.decrypt(row['cookies'])) if row['cookies'] else {},
    'csrf':               row['csrf'] or '',
    'access_expires_at':  row['access_expires_at'],
    'refresh_expires_at': row['refresh_expires_at'],
    'vinted_user_id':     row['vinted_user_id'],
    'zone':               row['zone'],
    'ip':                 row['ip'],
  }


# ── Refresh (worker) ──────────────────────────────────────────────────────────

async def due_for_refresh(
  conn: asyncpg.Connection, keepalive_before: timedelta, active_window: timedelta,
) -> list:
  """
  Active sessions to renew NOW, for one of two reasons:
    - offline keepalive: the refresh_token expires within `keepalive_before` (~2 days);
    - online freshness: the user is active (heartbeat within `active_window`) and
      the jittered `next_refresh_at` time has passed → keep the access token fresh.
  Includes the dedicated proxy's zone+IP (to redo the call from the same IP).
  """
  return await conn.fetch(
    """
    select s.user_id, s.refresh_token, s.cookies, p.zone, p.ip
    from public.vinted_sessions s
    left join public.proxy_pool p on p.id = s.proxy_id
    where s.status = 'active' and (
      s.refresh_expires_at <= now() + $1::interval
      or (s.last_active_at >= now() - $2::interval
          and s.next_refresh_at is not null and s.next_refresh_at <= now())
    )
    """,
    keepalive_before,
    active_window,
  )


async def get_coords(conn: asyncpg.Connection, user_id: str) -> tuple[float, float] | None:
  """VLF-11: coordinates already geocoded for the user (None if never computed)."""
  row = await conn.fetchrow(
    'select delivery_lat, delivery_lng from public.vinted_sessions where user_id = $1',
    user_id,
  )
  if row and row['delivery_lat'] is not None and row['delivery_lng'] is not None:
    return (row['delivery_lat'], row['delivery_lng'])
  return None


async def save_coords(conn: asyncpg.Connection, user_id: str, lat: float, lng: float) -> None:
  """VLF-11: store the coordinates (from the postal code) so it never re-geocodes again."""
  await conn.execute(
    'update public.vinted_sessions set delivery_lat = $2, delivery_lng = $3 where user_id = $1',
    user_id, lat, lng,
  )


async def touch_active(conn: asyncpg.Connection, user_id: str) -> None:
  """Heartbeat: mark that the user is online now (only if they have a session)."""
  await conn.execute(
    'update public.vinted_sessions set last_active_at = now() where user_id = $1',
    user_id,
  )


# ── Preferred pickup points (pickup_prefs) ────────────────────────────────────

async def save_pickup_pref(
  conn: asyncpg.Connection, user_id: str, carrier_code: str,
  point_code: str, point_uuid: str, name: str | None, address: str | None,
  distance_m: float | None = None,
) -> None:
  """Upsert the preferred point for a carrier (one per carrier per user)."""
  await conn.execute(
    """
    insert into public.pickup_prefs
      (user_id, carrier_code, point_code, point_uuid, name, address, distance_m, updated_at)
    values ($1,$2,$3,$4,$5,$6,$7, now())
    on conflict (user_id, carrier_code) do update set
      point_code = excluded.point_code,
      point_uuid = excluded.point_uuid,
      name       = excluded.name,
      address    = excluded.address,
      distance_m = excluded.distance_m,
      updated_at = now()
    """,
    user_id, carrier_code, point_code, point_uuid, name, address, distance_m,
  )


async def get_pickup_prefs(conn: asyncpg.Connection, user_id: str) -> list[dict]:
  rows = await conn.fetch(
    'select carrier_code, point_code, point_uuid, name, address, distance_m '
    'from public.pickup_prefs where user_id = $1',
    user_id,
  )
  return [dict(r) for r in rows]


async def get_pickup_prefs_map(conn: asyncpg.Connection, user_id: str) -> dict[str, dict]:
  """Cache of preferred points as a dict {carrier_code: {...}}."""
  rows = await conn.fetch(
    'select carrier_code, point_code, point_uuid, name, address, distance_m '
    'from public.pickup_prefs where user_id = $1',
    user_id,
  )
  return {r['carrier_code']: dict(r) for r in rows}


async def get_pickup_pref(conn: asyncpg.Connection, user_id: str, carrier_code: str) -> dict | None:
  row = await conn.fetchrow(
    'select carrier_code, point_code, point_uuid, name, address '
    'from public.pickup_prefs where user_id = $1 and carrier_code = $2',
    user_id, carrier_code,
  )
  return dict(row) if row else None


async def delete_pickup_pref(conn: asyncpg.Connection, user_id: str, carrier_code: str) -> None:
  await conn.execute(
    'delete from public.pickup_prefs where user_id = $1 and carrier_code = $2',
    user_id, carrier_code,
  )


# ── Purchase debug (non-success responses: 3DS, errors) ───────────────────────

async def log_buy_debug(
  conn: asyncpg.Connection, user_id: str, item_id, seller_id,
  payment_status: str | None, result, pickup,
) -> None:
  """Save the full response of a purchase that didn't cleanly succeed
  (3DS / requires_action / error) for future analysis."""
  await conn.execute(
    """
    insert into public.buy_debug
      (user_id, item_id, seller_id, payment_status, result, pickup)
    values ($1,$2,$3,$4,$5::jsonb,$6::jsonb)
    """,
    user_id, str(item_id), str(seller_id), payment_status,
    json.dumps(result, default=str),
    json.dumps(pickup, default=str) if pickup is not None else None,
  )


async def purge_buy_debug(conn: asyncpg.Connection, older_than_days: int) -> int:
  """VLF-07: delete purchase-debug records older than N days.
  They contain raw payment responses → they must not be kept forever."""
  if older_than_days <= 0:
    return 0
  row = await conn.fetchrow(
    "with d as (delete from public.buy_debug "
    "where created_at < now() - ($1 || ' days')::interval returning 1) "
    "select count(*) as n from d",
    str(older_than_days),
  )
  return int(row['n']) if row else 0


async def apply_refresh(
  conn: asyncpg.Connection, user_id: str,
  access_token: str, refresh_token: str, cookies: dict,
) -> None:
  """Save the renewed tokens and restart the expiries (access 2h, refresh 7d)."""
  now = _now()
  await conn.execute(
    """
    update public.vinted_sessions set
      access_token       = $2,
      refresh_token      = $3,
      cookies            = $4,
      access_expires_at  = $5,
      refresh_expires_at = $6,
      last_refresh_at    = $7,
      next_refresh_at    = $8,
      updated_at         = $7
    where user_id = $1
    """,
    user_id,
    token_crypto.encrypt(access_token),
    token_crypto.encrypt(refresh_token),
    token_crypto.encrypt(json.dumps(cookies)),
    now + ACCESS_TTL,
    now + REFRESH_TTL,
    now,
    _next_refresh_at(now),
  )


async def mark_expired(conn: asyncpg.Connection, user_id: str) -> None:
  await conn.execute(
    "update public.vinted_sessions set status = 'expired', updated_at = now() "
    "where user_id = $1",
    user_id,
  )

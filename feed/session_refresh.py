"""
session_refresh.py — Vinted session refresh SERIALIZED per-user.

The Vinted refresh_token is single-use: two concurrent refreshes for the same
user (periodic worker + on-demand refresh at buy time) would consume the same
token, one would fail, and the session would be wrongly marked `expired`
(SECURITY_AUDIT VLF-03). Here we serialize with a per-user asyncio lock and
RE-READ the token UNDER lock: if another path has already renewed it in the
meantime, we skip.

Note: the lock is IN-PROCESS. That is fine because the feed is a single process
(as _PENDING in vinted_api already assumes). If one day this scales to multiple
processes, a cross-process lock will be needed (an advisory lock in an explicit
transaction — the Supabase pooler does NOT support session-level locks — or Redis).
"""

import asyncio
import json

import token_crypto
import vinted_refresh
import vinted_store

# One lock per user. Grows by one Lock for each user that renews (negligible).
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(user_id: str) -> asyncio.Lock:
  lk = _locks.get(user_id)
  if lk is None:
    lk = asyncio.Lock()
    _locks[user_id] = lk
  return lk


async def locked_refresh(conn, user_id: str, proxy_url: str, need_if) -> str:
  """
  Refreshes the session serialized per-user. `need_if(row)` is evaluated UNDER
  lock against the re-read data: if False, someone else has already renewed it →
  nothing to do. Returns: 'refreshed' | 'fresh' | 'expired'.
  """
  async with _lock_for(user_id):
    row = await conn.fetchrow(
      """
      select status, access_expires_at, refresh_expires_at, last_active_at,
             next_refresh_at, refresh_token, cookies
      from public.vinted_sessions where user_id = $1
      """,
      user_id,
    )
    if row is None or row['status'] != 'active':
      return 'expired'
    if not need_if(row):
      return 'fresh'  # already renewed by another path → don't re-consume the token

    refresh_token = token_crypto.decrypt(row['refresh_token']) if row['refresh_token'] else ''
    cookies = json.loads(token_crypto.decrypt(row['cookies'])) if row['cookies'] else {}
    res = await vinted_refresh.refresh(refresh_token, proxy_url, cookies)
    if res.get('status') == 'success':
      await vinted_store.apply_refresh(
        conn, user_id, res['accessToken'], res['refreshToken'], res['cookies'],
      )
      return 'refreshed'
    await vinted_store.mark_expired(conn, user_id)
    return 'expired'

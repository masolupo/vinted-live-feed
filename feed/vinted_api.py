"""
vinted_api.py — endpoints for "Connect Vinted account" (login from the web UI).

2-step login (2FA is completed with the code entered by the user):
  POST   /vinted/login       {user_id, email, password}
  POST   /vinted/login/2fa   {user_id, code}
  GET    /vinted/status?user_id=
  DELETE /vinted/session?user_id=

Called ONLY by the Next backend, which forwards them with the x-internal-secret header.
Between the two login steps the VintedSession (with its connection open) stays in
memory in the feed process: _PENDING[user_id]. Single process → fine.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from os import getenv

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import geocode
import pickup_select
import pickup_setup
import proxy_pool
import rate_limit
import session_refresh
import vinted_store
from db import get_pool
from session import VintedSession

# Margin: if the access token expires within this time, it is refreshed before buying.
_ACCESS_MARGIN = timedelta(seconds=120)
# Maximum distance of a "not too far" pickup point (meters).
_MAX_DISTANCE_M = float(getenv('PICKUP_MAX_DISTANCE_M', '5000'))
# Validity window of the per-request signature (seconds) — anti-replay.
_SIG_WINDOW = int(getenv('FEED_SIG_WINDOW_SEC', '30'))

# Per-user rate limiting (limit, window seconds). See VLF-04.
_RL_LOGIN = (int(getenv('VINTED_LOGIN_RATE', '5')), float(getenv('VINTED_LOGIN_WINDOW', '300')))
_RL_2FA = (int(getenv('VINTED_2FA_RATE', '10')), float(getenv('VINTED_2FA_WINDOW', '300')))
_RL_BUY = (int(getenv('VINTED_BUY_RATE', '20')), float(getenv('VINTED_BUY_WINDOW', '60')))


def _ratelimit(action: str, user_id: str, conf: tuple):
  limit, window = conf
  if not rate_limit.allow(f'{action}:{user_id}', limit, window):
    raise HTTPException(status_code=429, detail='Too many requests, try again shortly')


async def _verify_request(
  request: Request,
  x_feed_ts: str | None = Header(default=None),
  x_feed_sig: str | None = Header(default=None),
):
  """
  Authenticate /vinted/* calls with a per-request SIGNATURE (not a static
  bearer): the secret never travels over the wire. Next signs
    HMAC-SHA256( "<ts>.<METHOD>.<path?query>.<body>", FEED_INTERNAL_SECRET )
  and sends x-feed-ts + x-feed-sig. Here we recompute and compare, rejecting if
  the timestamp is outside the window (anti-replay) or the signature doesn't match.
  See SECURITY_AUDIT VLF-02.
  """
  secret = getenv('FEED_INTERNAL_SECRET', '')
  if not secret or not x_feed_ts or not x_feed_sig:
    raise HTTPException(status_code=401, detail='missing signature')
  try:
    ts = int(x_feed_ts)
  except ValueError:
    raise HTTPException(status_code=401, detail='invalid timestamp')
  if abs(int(time.time()) - ts) > _SIG_WINDOW:
    raise HTTPException(status_code=401, detail='timestamp outside window')

  body = (await request.body()).decode('utf-8', 'replace')
  target = request.url.path + (f'?{request.url.query}' if request.url.query else '')
  msg = f'{x_feed_ts}.{request.method}.{target}.{body}'
  expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
  if not hmac.compare_digest(x_feed_sig, expected):
    raise HTTPException(status_code=401, detail='invalid signature')


# All /vinted/* routes require a valid signature (no exceptions).
router = APIRouter(prefix='/vinted', dependencies=[Depends(_verify_request)])

# Pending 2FA login: user_id → {'vs', 'proxy_id', 'ts'}. TTL 10 minutes.
_PENDING: dict[str, dict] = {}
_PENDING_TTL = 600

# Purchases in progress: (user_id, item_id) pairs for which a buy is "in flight".
# Prevents two CONCURRENT purchases of the same item (double click/retry). See VLF-05.
_inflight_buys: set[tuple[str, str]] = set()


def _require_pool():
  pool = get_pool()
  if pool is None:
    raise HTTPException(status_code=503, detail='DB not configured')
  return pool


def _gc_pending():
  now = time.time()
  for uid in [u for u, p in _PENDING.items() if now - p['ts'] > _PENDING_TTL]:
    _drop_pending(uid)


def _drop_pending(user_id: str):
  entry = _PENDING.pop(user_id, None)
  if entry:
    vs = entry.get('vs')
    if vs:
      # best-effort close of the curl_cffi connection left open
      import asyncio
      try:
        asyncio.create_task(vs.close())
      except Exception:
        pass


class LoginBody(BaseModel):
  user_id: str
  email: str
  password: str


class TwoFaBody(BaseModel):
  user_id: str
  code: str


class HeartbeatBody(BaseModel):
  user_id: str


class BuyBody(BaseModel):
  user_id: str
  item_id: str
  seller_id: str


class PickupSaveBody(BaseModel):
  user_id: str
  carrier_code: str
  point_code: str
  point_uuid: str
  name: str | None = None
  address: str | None = None


@router.post('/login')
async def vinted_login(body: LoginBody):
  _ratelimit('login', body.user_id, _RL_LOGIN)
  _gc_pending()
  pool = _require_pool()

  async with pool.acquire() as conn:
    proxy = await proxy_pool.assign(conn, body.user_id)
    if proxy is None:
      raise HTTPException(status_code=503, detail='No proxy available in the pool')

    vs = VintedSession(proxy=proxy['url'], email=body.email, password=body.password)
    res = await vs.start_login()
    status = res.get('status')

    if status == 'ok':
      await vinted_store.save(conn, body.user_id, vs, proxy['id'])
      await vs.close()
      return {'status': 'connected'}

    if status == '2fa_required':
      # Keep the session open to complete it via /login/2fa.
      _PENDING[body.user_id] = {'vs': vs, 'proxy_id': proxy['id'], 'ts': time.time()}
      return {'status': '2fa_required'}

    if status == 'ip_blocked':
      # IP rejected: mark it burned so the next attempt takes a different one.
      await proxy_pool.burn(conn, proxy['id'])
      await vs.close()
      return {'status': 'error', 'error': 'IP temporarily blocked, try again'}

    # Generic error (e.g. wrong credentials): release the proxy.
    await proxy_pool.release(conn, body.user_id)
    await vs.close()
    return {'status': 'error', 'error': res.get('reason', 'login failed')}


@router.post('/login/2fa')
async def vinted_login_2fa(body: TwoFaBody):
  _ratelimit('2fa', body.user_id, _RL_2FA)
  entry = _PENDING.get(body.user_id)
  if entry is None:
    raise HTTPException(status_code=410, detail='No pending login: sign in again')

  vs = entry['vs']
  res = await vs.submit_2fa(body.code)
  if res.get('status') == 'ok':
    pool = _require_pool()
    async with pool.acquire() as conn:
      await vinted_store.save(conn, body.user_id, vs, entry['proxy_id'])
    await vs.close()
    _PENDING.pop(body.user_id, None)
    return {'status': 'connected'}

  # Wrong code / failed: close and make the user start over.
  _drop_pending(body.user_id)
  return {'status': 'error', 'error': res.get('reason', 'verification failed')}


@router.post('/heartbeat')
async def vinted_heartbeat(body: HeartbeatBody):
  pool = _require_pool()
  async with pool.acquire() as conn:
    await vinted_store.touch_active(conn, body.user_id)
  return {'ok': True}


@router.get('/status')
async def vinted_status(user_id: str):
  pool = _require_pool()
  async with pool.acquire() as conn:
    return {'status': await vinted_store.get_status(conn, user_id)}


@router.delete('/session')
async def vinted_disconnect(user_id: str):
  _drop_pending(user_id)
  pool = _require_pool()
  async with pool.acquire() as conn:
    await vinted_store.delete(conn, user_id)
    await proxy_pool.release(conn, user_id)
  return {'status': 'disconnected'}


# ── Acquisto (fastbuy) ────────────────────────────────────────────────────────

@router.post('/buy')
async def vinted_buy(body: BuyBody):
  """STREAMING purchase (NDJSON): emits progress phase by phase, so the
  button shows 'Got it!' the instant the payment starts (= reservation)
  and then confirms with the pickup point.
  Events: {'phase': 'preparing'|'paying'|'done'|'requires_action'|'error', ...}."""
  _ratelimit('buy', body.user_id, _RL_BUY)
  key = (body.user_id, body.item_id)

  async def _stream():
    # Idempotency: in single-thread asyncio the check-and-add is atomic (no await).
    if key in _inflight_buys:
      yield json.dumps({'phase': 'error', 'error': 'A purchase is already in progress for this item'}) + '\n'
      return
    _inflight_buys.add(key)
    try:
      async for ev in _do_buy_events(body):
        yield json.dumps(ev, default=str) + '\n'
    except Exception as e:
      print(f'buy stream error: {type(e).__name__}: {str(e)[:160]}')
      yield json.dumps({'phase': 'error', 'error': 'Error during the purchase'}) + '\n'
    finally:
      _inflight_buys.discard(key)

  return StreamingResponse(_stream(), media_type='application/x-ndjson')


async def _do_buy_events(body: BuyBody):
  """Generator of the purchase progress events. See vinted_buy."""
  pool = _require_pool()
  item_id, seller_id = int(body.item_id), int(body.seller_id)
  t0 = time.perf_counter()
  yield {'phase': 'preparing'}  # the button shows 'Preparing…'

  result = None
  async with pool.acquire() as conn:
    vs = await _restored_session(conn, body.user_id)
    if vs is None:
      yield {'phase': 'error', 'error': 'Vinted account not connected or expired'}
      return
    t_sess = time.perf_counter()  # end of the session/refresh phase
    t_checkout = t_pickup = t_pay = t_sess
    try:
      # Open checkout. If it fails (stale cookies?), refresh and retry once.
      opened = await vs.open_checkout(item_id, seller_id)
      if opened.get('status') != 'ok':
        await vs.close()
        vs = await _restored_session(conn, body.user_id, force_refresh=True)
        if vs is None:
          yield {'phase': 'error', 'error': 'Vinted session expired — reconnect the account'}
          return
        opened = await vs.open_checkout(item_id, seller_id)
        if opened.get('status') != 'ok':
          # VLF-08: no dump of the Vinted response to the client (stays in the logs/buy_debug).
          print(f"buy: item {item_id} → checkout failed: {opened}")
          yield {'phase': 'error', 'error': opened.get('error', 'checkout failed')}
          return

      comps = opened['components']
      purchase_id = opened['purchase_id']
      t_checkout = time.perf_counter()  # end of checkout open (conversations+build)

      # Geocode the postal code ONLY if at least one of the item's carriers is not
      # cached (i.e. only if nearby_pickup_points will be needed). Warm cache → no geocode.
      lat = lng = None
      cached = await vinted_store.get_pickup_prefs_map(conn, body.user_id)
      carriers = pickup_setup.pickup_carriers(comps)
      if any(c.get('carrier_code') and c['carrier_code'] not in cached for c in carriers):
        # VLF-11: reuse the coordinates already geocoded for the user; query
        # Nominatim with the postal code only the FIRST time, then persist them.
        coords = await vinted_store.get_coords(conn, body.user_id)
        if coords is None:
          coords = await geocode.cap_to_coords(pickup_setup.postal_code(comps))
          if coords is None:
            yield {'phase': 'error', 'error': 'Could not determine the location (postal code) for the pickup point'}
            return
          await vinted_store.save_coords(conn, body.user_id, coords[0], coords[1])
        lat, lng = coords

      chosen = await pickup_select.choose(
        vs, conn, body.user_id, comps, lat, lng, _MAX_DISTANCE_M,
      )
      if chosen.get('status') != 'ok':
        yield {'phase': 'error', 'error': chosen.get('error')}
        return
      t_pickup = time.perf_counter()  # end of pickup-point selection (incl. cold nearby)

      # >>> the payment starts here → Vinted RESERVES the item (15 min) = 'Got it!'
      yield {'phase': 'paying'}

      result = await vs.pay_with_pickup(
        purchase_id, item_id, chosen['rate_uuid'], chosen['point_code'], chosen['point_uuid'],
      )
      t_pay = time.perf_counter()  # end of payment

      # Debug: save the full response if the payment is NOT a clean success
      # (3DS / requires_action / error) → future analysis.
      _ps = result.get('payment', {}).get('status') if isinstance(result, dict) else None
      if isinstance(result, dict) and ('error' in result or _ps != 'success'):
        try:
          await vinted_store.log_buy_debug(
            conn, body.user_id, item_id, seller_id, _ps or 'error', result,
            {'carrier': chosen.get('carrier_code'), 'point': chosen.get('point_code'),
             'distance_m': chosen.get('distance_m'), 'price': chosen.get('price')},
          )
        except Exception as e:
          print(f'buy_debug: logging failed: {e}')
    finally:
      await vs.close()

  dt = time.perf_counter() - t0
  if isinstance(result, dict) and 'error' in result:
    # VLF-08: Vinted detail only in the logs/buy_debug, not in the response to the client.
    print(f"buy: item {item_id} → ERROR: {result.get('error')} {result.get('status','')} [{dt:.2f}s] {result}")
    yield {'phase': 'error', 'error': result.get('error')}
    return
  payment_status = (result or {}).get('payment', {}).get('status', 'unknown')
  print(f"buy: item {item_id} → pickup {chosen['carrier_code']} "
        f"({chosen['point_code']}, {chosen.get('distance_m')}m, {chosen.get('price')}EUR) "
        f"payment={payment_status} "
        f"[tot {dt:.2f}s | sess {t_sess-t0:.2f} checkout {t_checkout-t_sess:.2f} "
        f"pickup {t_pickup-t_checkout:.2f} pay {t_pay-t_pickup:.2f}]")
  pickup = {
    'carrier':        chosen['carrier_code'],
    'point':          chosen['point_code'],
    'name':           chosen.get('name'),
    'address':        chosen.get('address'),
    'distance_m':     chosen.get('distance_m'),
    'shipping_price': chosen.get('price'),
  }
  # success → 'done'; 3DS/pending → 'requires_action' (item reserved for 15 min anyway).
  phase = 'done' if payment_status in ('success', 'completed') else (
    'requires_action' if payment_status in ('requires_action', 'pending') else 'done'
  )
  yield {'phase': phase, 'payment_status': payment_status, 'pickup': pickup}


# ── Pickup-point map setup ────────────────────────────────────────────────────

async def _restored_session(conn, user_id: str, force_refresh: bool = False):
  """Load the session from the DB, refresh it if needed (or if force_refresh), and
  return a ready VintedSession (restored session). None if not connected.
  force_refresh: for DataDome-sensitive calls (catalog/checkout) it's better to
  always start from fresh cookies."""
  sess = await vinted_store.load_session(conn, user_id)
  if sess is None or sess['status'] != 'active':
    return None
  proxy_url = proxy_pool.build_url(sess['zone'], sess['ip']) if sess['zone'] else ''
  ax = sess['access_expires_at']
  if force_refresh or ax is None or ax <= datetime.now(timezone.utc) + _ACCESS_MARGIN:
    def _need(r):
      if force_refresh:
        return True
      a = r['access_expires_at']
      return a is None or a <= datetime.now(timezone.utc) + _ACCESS_MARGIN

    outcome = await session_refresh.locked_refresh(conn, user_id, proxy_url, _need)
    if outcome == 'expired':
      return None
    # Reload the fresh cookies/tokens (the refresh updated them in the DB).
    sess = await vinted_store.load_session(conn, user_id)
    if sess is None or sess['status'] != 'active':
      return None

  vs = VintedSession(proxy=proxy_url)
  vs.restore_session(sess['cookies'], sess['csrf'])
  return vs


@router.post('/pickup/save')
async def vinted_pickup_save(body: PickupSaveBody):
  pool = _require_pool()
  async with pool.acquire() as conn:
    await vinted_store.save_pickup_pref(
      conn, body.user_id, body.carrier_code, body.point_code,
      body.point_uuid, body.name, body.address,
    )
  return {'status': 'ok'}


@router.get('/pickup/prefs')
async def vinted_pickup_prefs(user_id: str):
  pool = _require_pool()
  async with pool.acquire() as conn:
    prefs = await vinted_store.get_pickup_prefs(conn, user_id)
  return {'status': 'ok', 'prefs': prefs}

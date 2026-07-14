"""
VintedSession — Vinted login + purchase, multi-user.

Login (2-step, designed for the web UI):
  await vs.start_login()      → 'ok' | '2fa_required' | 'ip_blocked' | 'error'
  await vs.submit_2fa(code)   → 'ok' | 'error'

Credentials and proxy are PER USER (passed to the constructor), no longer from
a global env. CAPSOLVER_KEY stays a shared service key (from env, with an
optional override). Technique: curl_cffi (Chrome TLS) + dedicated ISP proxy
(BrightData, IP pinned with -ip-) + CapSolver (DataDome bypass).

After a successful login the instance exposes the following, to be persisted in
the DB to keep the session alive (see vinted_refresh.py):
  vs.access_token, vs.refresh_token, vs.cookies, vs.csrf, vs.vinted_user_id

Buy: 3 API calls in sequence:
  POST /api/v2/purchases/checkout/build        → purchase_id
  PUT  /api/v2/purchases/{id}/checkout         → checksum
  POST /api/v2/purchases/{id}/checkout/payment → payment outcome
"""

import asyncio
import base64
import json
import re
from os import getenv
from dotenv import load_dotenv
from curl_cffi.requests import AsyncSession
import httpx

load_dotenv()

# Optional defaults from env: handy for the CLI (test_buy.py). In the
# multi-user path they are passed explicitly to the constructor.
PICKUP_POINT_CODE = getenv('PICKUP_POINT_CODE', '')
PICKUP_POINT_UUID = getenv('PICKUP_POINT_UUID', '')

BASE_URL   = 'https://www.vinted.it'
DESKTOP_UA = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) '
  'Chrome/149.0.0.0 Safari/537.36'
)
# CapSolver ONLY supports a Windows UA → we present ourselves as Chrome 149 on Windows.
# impersonate=chrome146 gives the same TLS/HTTP2 fingerprint (JA4 identical to Chrome 149).
SEC_CH_UA = '"Chromium";v="149", "Google Chrome";v="149", "Not)A;Brand";v="24"'

# NAVIGATION headers (GET homepage) — Chrome 149 Windows.
# default_headers=False → curl_cffi adds nothing, we set them all ourselves.
_WEB_HEADERS = {
  'sec-ch-ua':                 SEC_CH_UA,
  'sec-ch-ua-mobile':          '?0',
  'sec-ch-ua-platform':        '"Windows"',
  'upgrade-insecure-requests': '1',
  'user-agent':                DESKTOP_UA,
  'accept':                    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
  'accept-language':           'it-IT,it;q=0.9',
  'sec-fetch-site':            'none',
  'sec-fetch-mode':            'navigate',
  'sec-fetch-user':            '?1',
  'sec-fetch-dest':            'document',
  'accept-encoding':           'gzip, deflate, br, zstd',
  'priority':                  'u=0, i',
}

# FETCH/XHR headers (API calls) — Chrome 149 fetch:
# no upgrade-insecure-requests / sec-fetch-user, priority u=1.
_API_BASE = {
  'content-type':       'application/json',
  'sec-ch-ua':          SEC_CH_UA,
  'sec-ch-ua-mobile':   '?0',
  'sec-ch-ua-platform': '"Windows"',
  'user-agent':         DESKTOP_UA,
  'accept':             'application/json, text/plain, */*',
  'accept-language':    'it-IT,it;q=0.9',
  'origin':             BASE_URL,
  'sec-fetch-site':     'same-origin',
  'sec-fetch-mode':     'cors',
  'sec-fetch-dest':     'empty',
  'referer':            f'{BASE_URL}/',
  'accept-encoding':    'gzip, deflate, br, zstd',
  'priority':           'u=1, i',
  'locale':             'it-IT',
}

# Fixed body for the PUT checkout — uses the profile's default settings
_CHECKOUT_COMPONENTS = {
  'components': {
    'additional_service':      {},
    'payment_method':          {},
    'shipping_address':        {},
    'shipping_pickup_options': {},
    'shipping_pickup_details': {},
  }
}

# Fixed browser_info for 3DS2 — plausible values, unchanged between purchases
_BROWSER_INFO = {
  'language':        'it-IT',
  'color_depth':     24,
  'java_enabled':    False,
  'screen_height':   1080,
  'screen_width':    1920,
  'timezone_offset': -120,  # UTC+2 (Italy, daylight saving time)
}


# ── Helper functions (module-level) ───────────────────────────────────────────

def _decode_jwt_payload(token: str) -> dict:
  """Decode a JWT payload (without verifying the signature)."""
  payload_b64 = token.split('.')[1]
  # Add base64 padding if needed
  payload_b64 += '=' * (4 - len(payload_b64) % 4)
  return json.loads(base64.urlsafe_b64decode(payload_b64))


def _extract_csrf(text: str) -> str:
  """Extract the CSRF token from the homepage HTML."""
  for pattern in [
    r'\\?"CSRF_TOKEN\\?":\s*\\?"([a-f0-9-]{36})\\?"',
    r'"CSRF_TOKEN"\s*:\s*"([^"]+)"',
    r'"csrf_token"\s*:\s*"([^"]+)"',
    r'"csrfToken"\s*:\s*"([^"]+)"',
    r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
  ]:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
      return m.group(1)
  return ''


async def _solve_datadome(challenge_url: str, proxy: str, capsolver_key: str) -> str | None:
  """Solve a DataDome challenge via CapSolver. Returns the datadome cookie value."""
  task_type = 'DatadomeSliderTask' if 'captcha' in challenge_url else 'AntiDatadomeTaskProxyLess'
  print(f'      CapSolver: type={task_type}')

  async with httpx.AsyncClient(timeout=120) as client:
    r = await client.post('https://api.capsolver.com/createTask', json={
      'clientKey': capsolver_key,
      'task': {
        'type':       task_type,
        'websiteURL': BASE_URL,
        'captchaUrl': challenge_url,
        'userAgent':  DESKTOP_UA,
        'proxy':      proxy,
      }
    })
    data = r.json()
    task_id = data.get('taskId')
    if not task_id:
      print(f'      CapSolver error: {data}')
      return None

    print(f'      task_id: {task_id} — waiting...')
    for attempt in range(30):
      await asyncio.sleep(3)
      r2 = await client.post('https://api.capsolver.com/getTaskResult',
                   json={'clientKey': capsolver_key, 'taskId': task_id})
      result = r2.json()
      status = result.get('status')
      print(f'      attempt {attempt + 1}: {status}')

      if status == 'ready':
        cookie = result.get('solution', {}).get('cookie', '')
        # CapSolver returns the FULL cookie ("datadome=VALUE; Max-Age=…; …"):
        # we extract ONLY the token, otherwise the cookie is malformed → 403.
        value = cookie.split(';', 1)[0].strip().removeprefix('datadome=')
        print('      datadome solved')
        return value
      if status == 'failed':
        print(f'      CapSolver failed: {result}')
        return None

  print('      CapSolver timeout')
  return None


# ── Main class ────────────────────────────────────────────────────────────────

class VintedSession:
  """
  Vinted session for ONE user: login (possibly 2FA), then purchases, with the
  same dedicated proxy/IP and the same cookies. Credentials and proxy are per
  user; CAPSOLVER_KEY is a shared service key.
  """

  def __init__(
    self,
    proxy: str | None = None,
    email: str | None = None,
    password: str | None = None,
    capsolver_key: str | None = None,
  ):
    # Per user (fallback to env for the CLI / test_buy.py).
    self._proxy:    str = proxy    or getenv('PROXY_BRD', '')
    self._email:    str = email    or getenv('VINTED_EMAIL', '')
    self._password: str = password or getenv('VINTED_PASSWORD', '')
    self._capsolver_key: str = capsolver_key or getenv('CAPSOLVER_KEY', '')

    # Session state.
    self._session: AsyncSession | None = None
    self._csrf:    str = ''

    # Transient state for 2FA (between start_login and submit_2fa).
    self._control_code:  str = ''
    self._login_headers: dict | None = None

    # Output of a successful login (to be persisted in the DB).
    self.access_token:   str = ''
    self.refresh_token:  str = ''
    self.cookies:        dict = {}
    self.csrf:           str = ''
    self.vinted_user_id: str = ''

  # ── Header builder ────────────────────────────────────────────────────────

  def _headers(self, referer: str | None = None) -> dict:
    """Build the API headers, adding CSRF and anon_id from the active session."""
    anon_id = self._session.cookies.get('anon_id', '') if self._session else ''
    return {
      # 'referer' is already in _API_BASE (lowercase) → here it updates it in place,
      # avoiding a duplicate 'Referer'/'referer'.
      **_API_BASE,
      'referer':      referer or f'{BASE_URL}/',
      'x-csrf-token': self._csrf,
      'x-anon-id':    anon_id,
    }

  def _normalized_proxy(self) -> str:
    p = self._proxy
    return p if p.startswith('http') else f'http://{p}'

  async def _post_login(self, session: AsyncSession, headers: dict):
    """POST credentials (grant_type=password)."""
    return await session.post(
      f'{BASE_URL}/web/api/auth/oauth',
      json={
        'client_id':   'web',
        'scope':       'user',
        'username':    self._email,
        'password':    self._password,
        'fingerprint': '7c79b1ce394f54bfb5e81860f58c446f',
        'grant_type':  'password',
      },
      headers=headers,
      timeout=20,
    )

  # ── Login: step 1 (credenziali) ───────────────────────────────────────────

  async def start_login(self) -> dict:
    """
    Start the login using the user's dedicated IP.

    Returns a dict with 'status':
      'ok'           → logged in; tokens are ready (self.access_token, ...)
      '2fa_required' → Vinted asks for the email code; call submit_2fa(code).
                       Response: {'status': '2fa_required', 'control_code': str}
      'ip_blocked'   → the IP is blocked (t=bv): it must be replaced/marked burned.
      'error'        → failed; 'reason' field (+ optional 'http_status').
    """
    missing = [n for n, v in {
      'email': self._email, 'password': self._password,
      'proxy': self._proxy, 'capsolver_key': self._capsolver_key,
    }.items() if not v]
    if missing:
      return {'status': 'error', 'reason': f'missing parameters: {", ".join(missing)}'}

    proxy = self._normalized_proxy()
    print(f'=== Vinted login (proxy {proxy.split("@")[-1]}) ===')
    # Chrome TLS impersonation; default_headers=False → only the headers we define.
    session = AsyncSession(impersonate='chrome146', proxy=proxy, verify=False, default_headers=False)

    try:
      # ── Step 1: GET homepage → initial cookies + CSRF ─────────────────
      print('   1. GET homepage...')
      r = await session.get(BASE_URL, headers=_WEB_HEADERS, timeout=15)
      print(f'      status: {r.status_code}')
      csrf = _extract_csrf(r.text)
      print(f'      CSRF: {"ok" if csrf else "not found"}')

      login_headers = {**_API_BASE, 'x-csrf-token': csrf}

      # ── Step 2: POST login ─────────────────────────────────────────────
      print('   2. POST login...')
      r2 = await self._post_login(session, login_headers)
      print(f'      status: {r2.status_code}')

      # ── DataDome 403 ───────────────────────────────────────────────────
      if r2.status_code == 403:
        challenge_url = ''
        try:
          challenge_url = r2.json().get('url', '')
        except Exception:
          pass
        if not challenge_url:
          await session.close()
          return {'status': 'error', 'reason': '403 without challenge URL'}
        if 't=bv' in challenge_url:
          await session.close()
          return {'status': 'ip_blocked', 'reason': 'IP blocked (t=bv)'}

        print('      DataDome (t=fe) → CapSolver...')
        dd_value = await _solve_datadome(challenge_url, proxy, self._capsolver_key)
        if not dd_value:
          await session.close()
          return {'status': 'error', 'reason': 'CapSolver failed'}
        session.cookies.set('datadome', dd_value, domain='.vinted.it')
        print('      Retrying login with datadome...')
        r2 = await self._post_login(session, login_headers)
        print(f'      status: {r2.status_code}')

      # ── 2FA: suspend and ask the caller for the code ───────────────────
      if r2.status_code == 401:
        control_code = r2.json().get('payload', {}).get('id', '')
        print(f'      2FA required (control_code: {control_code})')
        # Keep the session open to complete it via submit_2fa().
        self._session       = session
        self._csrf          = csrf
        self._control_code  = control_code
        self._login_headers = login_headers
        return {'status': '2fa_required', 'control_code': control_code}

      if r2.status_code != 200:
        await session.close()
        return {'status': 'error', 'reason': 'login failed',
                'http_status': r2.status_code, 'body': r2.text[:300]}

      # ── Direct success (no 2FA) ────────────────────────────────────────
      await self._finalize(session, csrf)
      return {'status': 'ok'}

    except Exception as e:
      try:
        await session.close()
      except Exception:
        pass
      return {'status': 'error', 'reason': f'exception: {e}'}

  # ── Login: step 2 (codice 2FA) ────────────────────────────────────────────

  async def submit_2fa(self, code: str) -> dict:
    """Complete the login by sending the 2FA code received by email."""
    if not self._session or not self._control_code:
      return {'status': 'error', 'reason': 'no pending 2FA login'}

    session = self._session
    proxy   = self._normalized_proxy()

    async def _post_verify():
      return await session.post(
        f'{BASE_URL}/web/api/auth/oauth',
        json={
          'client_id':         'web',
          'scope':             'user',
          'grant_type':        'password',
          'password_type':     'two_factor_challenge_code',
          'control_code':      self._control_code,
          'verification_code': code,
          'is_trusted_device': True,
        },
        headers=self._login_headers,
        timeout=20,
      )

    try:
      r = await _post_verify()
      print(f'      2FA status: {r.status_code}')

      # DataDome on the verification too.
      if r.status_code == 403:
        challenge_url = ''
        try:
          challenge_url = r.json().get('url', '')
        except Exception:
          pass
        if challenge_url and 't=bv' not in challenge_url:
          dd_value = await _solve_datadome(challenge_url, proxy, self._capsolver_key)
          if dd_value:
            session.cookies.set('datadome', dd_value, domain='.vinted.it')
            r = await _post_verify()
            print(f'      2FA status after datadome: {r.status_code}')

      if r.status_code != 200:
        await session.close()
        self._session = None
        return {'status': 'error', 'reason': '2FA failed',
                'http_status': r.status_code, 'body': r.text[:300]}

      self._control_code  = ''
      self._login_headers = None
      await self._finalize(session, self._csrf)
      return {'status': 'ok'}

    except Exception as e:
      return {'status': 'error', 'reason': f'2FA exception: {e}'}

  # ── Finalization: extract tokens/cookies to save ──────────────────────────

  async def _finalize(self, session: AsyncSession, csrf: str):
    """
    Successful login: set the missing cookies (v_uid/v_sid from the JWT), refresh
    the authenticated CSRF, and capture access/refresh tokens + cookies to persist.
    """
    access_token = session.cookies.get('access_token_web', '')
    v_uid = ''
    if access_token:
      try:
        payload = _decode_jwt_payload(access_token)
        v_uid = str(payload.get('sub', ''))
        v_sid = payload.get('sid', '')
        if v_uid:
          session.cookies.set('v_uid', v_uid, domain='.vinted.it')
        if v_sid:
          session.cookies.set('v_sid', v_sid, domain='.vinted.it')
        # VLF-09: we don't log v_uid/v_sid (session identifiers).
        print(f'      identity extracted from the JWT ({"ok" if v_uid else "empty"})')
      except Exception as e:
        print(f'      Warning: could not extract v_uid/v_sid from the JWT: {type(e).__name__}')

    # The pre-login CSRF is not valid for post-login APIs: re-GET the homepage while logged in.
    print('   Refreshing CSRF post-login...')
    try:
      r_csrf = await session.get(BASE_URL, headers=_WEB_HEADERS, timeout=15)
      fresh_csrf = _extract_csrf(r_csrf.text)
      if fresh_csrf:
        csrf = fresh_csrf
        print('      new CSRF obtained')
    except Exception as e:
      print(f'      Warning: CSRF refresh failed: {e}')

    self._session       = session
    self._csrf          = csrf
    self.csrf           = csrf
    self.vinted_user_id = v_uid
    self.access_token   = session.cookies.get('access_token_web', '')
    self.refresh_token  = session.cookies.get('refresh_token_web', '')
    self.cookies        = {k: session.cookies.get(k) for k in session.cookies.keys()}
    print(f'   ✅ Login OK ({len(self.cookies)} cookies)')

  # ── Restore a saved session (to buy without logging in again) ─────────────

  def restore_session(self, cookies: dict, csrf: str) -> None:
    """
    Rebuild a session ready for buy() from the data saved in the DB:
    opens an AsyncSession on the dedicated proxy and rehydrates cookies + CSRF.
    Does no networking: it's only for the subsequent purchase calls.
    """
    session = AsyncSession(
      impersonate='chrome146', proxy=self._normalized_proxy(),
      verify=False, default_headers=False,
    )
    for k, v in (cookies or {}).items():
      if v is not None:
        try:
          session.cookies.set(k, v, domain='.vinted.it')
        except Exception:
          pass
    self._session = session
    self._csrf = csrf
    self.cookies = cookies or {}

  # ── Open checkout (no payment) — for the pickup-point map setup ────────────

  async def open_checkout(self, item_id: int, seller_id: int) -> dict:
    """
    Runs conversations → build and returns `purchase_id` + the checkout
    `components` (already complete: pickup carriers, rate_uuid, shipping_order_id,
    postal code), WITHOUT paying. The "empty" PUT checkout is useless: build
    already contains everything (verified). The order stays pending and expires:
    no purchase. Requires restore_session() (or login) first.
    """
    if not self._session:
      return {'status': 'error', 'error': 'session not active'}

    # Step 0: conversations → order_id
    r0 = await self._session.post(
      f'{BASE_URL}/api/v2/conversations',
      json={'initiator': 'buy', 'item_id': str(item_id), 'opposite_user_id': str(seller_id)},
      headers=self._headers(referer=f'{BASE_URL}/items/{item_id}'),
      timeout=15,
    )
    if r0.status_code != 200:
      return {'status': 'error', 'error': 'conversations failed',
              'http_status': r0.status_code, 'body': r0.text[:300]}
    conv = r0.json()
    order_id = (
      conv.get('conversation', {}).get('transaction', {}).get('id')
      or conv.get('conversation', {}).get('order_id')
      or conv.get('order_id')
    )
    if not order_id:
      return {'status': 'error', 'error': 'order_id not found', 'body': str(conv)[:300]}

    # Step 1: build → purchase_id + components (already complete: carriers, rate_uuid,
    # shipping_order_id, address). No "empty" PUT.
    r1 = await self._session.post(
      f'{BASE_URL}/api/v2/purchases/checkout/build',
      json={'purchase_items': [{'id': order_id, 'type': 'transaction'}]},
      headers=self._headers(referer=f'{BASE_URL}/items/{item_id}'),
      timeout=15,
    )
    if r1.status_code != 200:
      return {'status': 'error', 'error': 'checkout/build failed',
              'http_status': r1.status_code, 'body': r1.text[:300]}
    checkout = r1.json().get('checkout', {})
    purchase_id = checkout.get('id')
    components = checkout.get('components', {})
    if not purchase_id:
      return {'status': 'error', 'error': 'purchase_id not found', 'body': r1.text[:300]}

    return {'status': 'ok', 'purchase_id': purchase_id, 'components': components}

  async def pay_with_pickup(
    self, purchase_id: str, item_id: int,
    rate_uuid: str, point_code: str, point_uuid: str, incognia_token: str = '',
  ) -> dict:
    """
    Complete the purchase after open_checkout: set the chosen pickup point
    (PUT checkout), get the checksum, and pay. Returns the payment response
    (or {'error': ...} with an optional HTTP 'status').
    """
    if not self._session:
      return {'error': 'session not active'}
    extra = {'x-incognia-request-token': incognia_token} if incognia_token else {}
    referer = f'{BASE_URL}/checkout?purchase_id={purchase_id}'

    # PUT checkout with the pickup point.
    r = await self._session.put(
      f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout',
      json={'components': {
        'additional_service':      {},
        'payment_method':          {},
        'shipping_address':        {},
        'shipping_pickup_options': {},
        'shipping_pickup_details': {
          'rate_uuid':  rate_uuid,
          'point_code': point_code,
          'point_uuid': point_uuid,
        },
      }},
      headers=self._headers(referer=referer),
      timeout=15,
    )
    if r.status_code != 200:
      return {'error': 'PUT checkout pickup failed', 'status': r.status_code, 'body': r.text[:300]}
    try:
      checksum = r.json()['checkout']['checksum']
    except (KeyError, ValueError) as e:
      return {'error': f'checksum not found: {e}', 'body': r.text[:300]}

    # POST payment.
    r3 = await self._session.post(
      f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout/payment',
      json={'checksum': checksum, 'payment_options': {'browser_info': _BROWSER_INFO}},
      headers={**self._headers(referer=referer), **extra},
      timeout=20,
    )
    try:
      return r3.json()
    except Exception:
      return {'error': 'payment: non-JSON response', 'status': r3.status_code, 'body': r3.text[:300]}

  # ── Buy ───────────────────────────────────────────────────────────────────

  async def buy(self, item_id: int, seller_id: int, incognia_token: str = '') -> dict:
    """
    Buy a Vinted item in 4 steps.
    Requires that the login has already completed successfully.
    Returns the dict of the final response (contains payment.status).
    """
    if not self._session:
      return {'error': 'session not active — log in first'}

    print(f'\n=== Buying item {item_id} ===')

    extra = {'x-incognia-request-token': incognia_token} if incognia_token else {}

    # ── Step 0: POST conversations → order_id ────────────────────────────
    print('   0. POST conversations...')
    r0b = await self._session.post(
      f'{BASE_URL}/api/v2/conversations',
      json={
        'initiator':        'buy',
        'item_id':          str(item_id),
        'opposite_user_id': str(seller_id),
      },
      headers=self._headers(referer=f'{BASE_URL}/items/{item_id}'),
      timeout=15,
    )
    print(f'       status: {r0b.status_code}')
    if r0b.status_code != 200:
      # VLF-09: dump the body only on error (not on the happy path).
      print(f'       response: {r0b.text[:300]}')
      return {'error': 'POST conversations failed', 'status': r0b.status_code, 'body': r0b.text[:300]}

    conv = r0b.json()
    # Look for order_id in the most likely paths.
    order_id = (
      conv.get('conversation', {}).get('transaction', {}).get('id')
      or conv.get('conversation', {}).get('order_id')
      or conv.get('order_id')
    )
    if not order_id:
      return {'error': 'order_id not found in the conversations response', 'body': str(conv)[:500]}

    print(f'       order_id: {order_id}')

    # ── Step 1: start the checkout ─────────────────────────────────────────
    print('   1. POST checkout/build...')
    r1 = await self._session.post(
      f'{BASE_URL}/api/v2/purchases/checkout/build',
      json={'purchase_items': [{'id': order_id, 'type': 'transaction'}]},
      headers={**self._headers(referer=f'{BASE_URL}/items/{item_id}'), **extra},
      timeout=15,
    )
    print(f'      status: {r1.status_code}')

    if r1.status_code != 200:
      return {'error': 'checkout/build failed', 'status': r1.status_code, 'body': r1.text[:300]}

    try:
      purchase_id = r1.json()['checkout']['id']
    except (KeyError, ValueError) as e:
      return {'error': f'purchase_id not found: {e}', 'body': r1.text[:300]}

    print(f'      purchase_id: {purchase_id}')
    checkout_referer = f'{BASE_URL}/checkout?purchase_id={purchase_id}'

    # ── Step 2: configure the checkout, get the checksum ───────────────────
    print('   2. PUT checkout...')
    r2 = await self._session.put(
      f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout',
      json=_CHECKOUT_COMPONENTS,
      headers=self._headers(referer=checkout_referer),
      timeout=15,
    )
    print(f'      status: {r2.status_code}')
    if r2.status_code != 200:
      return {'error': 'PUT checkout failed', 'status': r2.status_code, 'body': r2.text[:300]}

    comps       = r2.json().get('checkout', {}).get('components', {})
    pickup_opts = comps.get('shipping_pickup_options', {})

    if pickup_opts.get('selected_pickup_option') == 2:
      rate_uuid = pickup_opts.get('pickup_options', {}).get('pickup', {}).get('selected_rate_uuid', '')

      if PICKUP_POINT_CODE and PICKUP_POINT_UUID and rate_uuid:
        print(f'      Confirming pickup point {PICKUP_POINT_CODE}...')
        r2 = await self._session.put(
          f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout',
          json={'components': {
            'additional_service':      {},
            'payment_method':          {},
            'shipping_address':        {},
            'shipping_pickup_options': {},
            'shipping_pickup_details': {
              'rate_uuid':  rate_uuid,
              'point_code': PICKUP_POINT_CODE,
              'point_uuid': PICKUP_POINT_UUID,
            },
          }},
          headers=self._headers(referer=checkout_referer),
          timeout=15,
        )
        print(f'      PUT pickup status: {r2.status_code}')
      else:
        home_options = comps.get('shipping_pickup_details', {}).get('pickup_types', {}).get('home', {}).get('shipping_options', [])
        if not home_options:
          return {'error': 'no shipping option available — configure PICKUP_POINT_CODE and PICKUP_POINT_UUID'}
        cheapest = min(home_options, key=lambda o: o.get('price', {}).get('amount', 999))
        print(f'      No pickup configured → home delivery ({cheapest["title"]}, {cheapest["price"]["amount"]}€)')
        r2 = await self._session.put(
          f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout',
          json={'components': {
            'additional_service':      {},
            'payment_method':          {},
            'shipping_address':        {},
            'shipping_pickup_options': {'selected_pickup_option': 1, 'selected_rate_uuid': cheapest['rate_uuid']},
            'shipping_pickup_details': {},
          }},
          headers=self._headers(referer=checkout_referer),
          timeout=15,
        )
        print(f'      PUT home status: {r2.status_code}')

      if r2.status_code != 200:
        return {'error': 'PUT shipping failed', 'status': r2.status_code, 'body': r2.text[:300]}

    try:
      checksum = r2.json()['checkout']['checksum']
    except (KeyError, ValueError) as e:
      return {'error': f'checksum not found: {e}', 'body': r2.text[:300]}

    print(f'      checksum: {checksum[:40]}...')

    # ── Step 3: pay ────────────────────────────────────────────────────────
    print('   3. POST payment...')
    r3 = await self._session.post(
      f'{BASE_URL}/api/v2/purchases/{purchase_id}/checkout/payment',
      json={
        'checksum':        checksum,
        'payment_options': {'browser_info': _BROWSER_INFO},
      },
      headers={**self._headers(referer=checkout_referer), **extra},
      timeout=20,
    )
    print(f'      status: {r3.status_code}')

    result = r3.json()
    payment_status = result.get('payment', {}).get('status', 'unknown')
    print(f'      payment status: {payment_status}')
    return result

  # ── Cleanup ───────────────────────────────────────────────────────────────

  async def close(self):
    """Close the HTTP session."""
    if self._session:
      await self._session.close()
      self._session = None
      print('Session closed.')

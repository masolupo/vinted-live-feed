"""
VintedRefresh — renews the Vinted access_token without logging in again.

Called by the server when a purchase fails with 401 (expired access_token).
The Vinted access_token lasts ~2h, the refresh_token ~7 days.

Uses the user's own dedicated proxy to keep IP/session consistency.
"""

from curl_cffi.requests import AsyncSession


BASE_URL   = 'https://www.vinted.it'
DESKTOP_UA = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) '
  'Chrome/142.0.0.0 Safari/537.36'
)

_REFRESH_HEADERS = {
  'User-Agent':   DESKTOP_UA,
  'Accept':       'application/json,text/plain,*/*',
  'Content-Type': 'application/json',
  'Origin':       BASE_URL,
  'Referer':      f'{BASE_URL}/',
}


async def refresh(refresh_token: str, proxy: str, cookies: dict | None = None) -> dict:
  """
  Renews the access_token by calling /web/api/auth/oauth with grant_type=refresh_token.

  Returns:
    {'status': 'success', 'accessToken': str, 'refreshToken': str, 'cookies': dict}
      → refreshToken may be the same one passed in if Vinted does not rotate it
    {'status': 'error', 'reason': str, 'http_status': int, 'body': str}
  """
  proxy = proxy if proxy.startswith('http') else f'http://{proxy}'
  session = AsyncSession(impersonate='chrome142', proxy=proxy, verify=False)

  # Rehydrate existing cookies (useful for the datadome cookie).
  if cookies:
    for k, v in cookies.items():
      if v is not None:
        session.cookies.set(k, v, domain='.vinted.it')

  try:
    print('=== Refresh access_token ===')
    r = await session.post(
      f'{BASE_URL}/web/api/auth/oauth',
      json={
        'client_id':     'web',
        'grant_type':    'refresh_token',
        'refresh_token': refresh_token,
      },
      headers=_REFRESH_HEADERS,
      timeout=20,
    )
    print(f'   status: {r.status_code}')

    try:
      body = r.json()
    except Exception:
      body = {}

    if r.status_code != 200:
      return {
        'status':      'error',
        'reason':      'refresh failed',
        'http_status': r.status_code,
        'body':        r.text[:1000],
      }

    new_access  = session.cookies.get('access_token_web', '')  or body.get('access_token', '')
    # If Vinted doesn't rotate the refresh token, reuse the old one.
    new_refresh = (
      session.cookies.get('refresh_token_web', '')
      or body.get('refresh_token', '')
      or refresh_token
    )

    if not new_access:
      return {
        'status':      'error',
        'reason':      'access_token not found in response',
        'http_status': r.status_code,
        'body':        str(body)[:1000],
      }

    merged_cookies = {k: session.cookies.get(k) for k in session.cookies.keys()}
    print('   ✅ Refresh OK')

    return {
      'status':       'success',
      'accessToken':  new_access,
      'refreshToken': new_refresh,
      'cookies':      merged_cookies,
    }

  except Exception as e:
    return {'status': 'error', 'reason': f'exception: {e}', 'http_status': 0, 'body': ''}
  finally:
    try:
      await session.close()
    except Exception:
      pass

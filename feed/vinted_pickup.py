"""
VintedPickup — Vinted pickup points.

Two responsibilities:
  - fetch_nearby_points(): calls the Vinted nearby_pickup_points endpoint and
    normalizes the points (for the "cold" map and for the buy).
  - select_pickup(): a PURE function that, given the list of points available for
    a transaction, the user's preferred points and the spending cap, picks which
    point to use. Testable without Vinted.

Endpoint:
  GET https://api.vinted.it/shipping-estimation/external/shipping_orders/
      {shipping_order_id}/nearby_pickup_points?country_code=IT&latitude=..&longitude=..

The shipping_order_id is a reusable context token (not tied to geography): a
cached one is enough for the cold map; at buy time the transaction's real one is
used, so rate_uuid and availability are correct for that item.
"""

API_URL = 'https://api.vinted.it'


def _to_float(v, default=None):
  try:
    return float(v)
  except (TypeError, ValueError):
    return default


def _rate_price(rate: dict) -> float | None:
  """The price charged to the buyer for a given rate."""
  for key in ('receiver_final_price', 'price'):
    amount = rate.get(key, {}).get('amount')
    p = _to_float(amount)
    if p is not None:
      return p
  return None


def normalize_points(body: dict) -> list[dict]:
  """
  Flattens shipping_points + shipping_rates into a convenient list.
  Each point already carries its rate_uuid; the price is taken from the matching
  rate (by rate_uuid).
  """
  rates_by_uuid = {r['rate_uuid']: r for r in body.get('shipping_rates', [])}
  out: list[dict] = []
  for sp in body.get('shipping_points', []):
    p = sp.get('point', {})
    rate_uuid = p.get('rate_uuid', '')
    rate = rates_by_uuid.get(rate_uuid, {})
    out.append({
      'code':         p.get('code', ''),
      'uuid':         p.get('uuid', ''),
      'name':         p.get('name', ''),
      'address':      p.get('address_line1', ''),
      'city':         p.get('city', ''),
      'postal_code':  p.get('postal_code', ''),
      'lat':          _to_float(p.get('latitude')),
      'lng':          _to_float(p.get('longitude')),
      'carrier_code': p.get('carrier_code', ''),
      'carrier_name': rate.get('title', ''),
      'point_type':   p.get('point_type', ''),
      'distance':     _to_float(sp.get('distance'), 1e9),
      'rate_uuid':    rate_uuid,
      'price':        _rate_price(rate),
    })
  return out


def select_pickup(
  points: list[dict],
  preferred_codes: set[str],
  max_price: float | None,
) -> dict | None:
  """
  Picks the pickup point to use for a purchase. PURE (no I/O).

  Rules (decided with the user):
    1. discard points above the spending cap (if set);
    2. among the available PREFERRED points → the cheapest;
    3. otherwise (no preferred) → the nearest available;
    4. if no point qualifies → None (the purchase should be skipped/handled upstream).

  A point is "valid" if it has both a rate_uuid and a price.
  """
  candidates = [
    p for p in points
    if p.get('rate_uuid') and p.get('price') is not None
    and (max_price is None or p['price'] <= max_price)
  ]
  if not candidates:
    return None

  preferred = [p for p in candidates if p['code'] in preferred_codes]
  if preferred:
    return min(preferred, key=lambda p: p['price'])

  return min(candidates, key=lambda p: p['distance'])


async def fetch_nearby_points(
  session,
  shipping_order_id: str,
  latitude: float,
  longitude: float,
  country_code: str = 'IT',
  headers: dict | None = None,
) -> dict:
  """
  Calls nearby_pickup_points and returns the normalized points.
    {'status': 'success', 'points': [...]}
    {'status': 'error', 'reason': str, 'http_status': int, 'body': str}
  `session` is an already-authenticated curl_cffi AsyncSession (cookies + proxy).
  `headers` are the API headers (User-Agent etc.): without them, Vinted returns 403.
  """
  url = (
    f'{API_URL}/shipping-estimation/external/shipping_orders/'
    f'{shipping_order_id}/nearby_pickup_points'
  )
  try:
    r = await session.get(
      url,
      params={
        'country_code': country_code,
        'latitude':     latitude,
        'longitude':    longitude,
      },
      headers=headers,
      timeout=15,
    )
    if r.status_code == 401:
      return {'status': 'auth_error'}
    if r.status_code != 200:
      return {
        'status':      'error',
        'reason':      'nearby_pickup_points failed',
        'http_status': r.status_code,
        'body':        r.text[:1000],
      }
    return {'status': 'success', 'points': normalize_points(r.json())}
  except Exception as e:
    return {'status': 'error', 'reason': f'exception: {e}', 'http_status': 0, 'body': ''}

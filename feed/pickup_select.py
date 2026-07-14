"""
pickup_select.py — picks the pickup point for a purchase (Design A + cache).

Rule: among the item's PICKUP carriers, the CHEAPEST one that has a point within
`max_distance_m`; if none is within the threshold, the absolute NEAREST one.
Never home delivery.

Cache: the nearest point per carrier is stored in pickup_prefs (with distance).
`nearby_pickup_points` is called ONLY for carriers not yet in cache → from the
second purchase with the same carrier the choice is instant (no call).
"""

import pickup_setup
import vinted_pickup
import vinted_store


def _price(c) -> float:
  try:
    return float(c.get('price'))
  except (TypeError, ValueError):
    return 1e9


def _dist(c) -> float:
  d = c.get('distance_m')
  return d if d is not None else 1e9


async def choose(vs, conn, user_id: str, components: dict,
                 lat: float, lng: float, max_distance_m: float) -> dict:
  """Returns {'status':'ok', rate_uuid, point_code, point_uuid, carrier_code,
  distance_m, price} or {'status':'error', 'error':...}."""
  carriers = [
    c for c in pickup_setup.pickup_carriers(components)
    if c.get('carrier_code') and c.get('rate_uuid')
  ]
  if not carriers:
    return {'status': 'error', 'error': 'No carrier with a pickup point for this item'}

  soid = pickup_setup.shipping_order_id(components)
  cached = await vinted_store.get_pickup_prefs_map(conn, user_id)

  # Item carriers with no cached point → a single nearby call covers them all.
  missing = [c for c in carriers if c['carrier_code'] not in cached]
  if missing and soid and lat is not None and lng is not None:
    res = await vinted_pickup.fetch_nearby_points(
      vs._session, str(soid), lat, lng, headers=vs._headers(),
    )
    if res.get('status') == 'success':
      nearest: dict[str, dict] = {}
      for p in res['points']:
        cc = p.get('carrier_code')
        if not cc:
          continue
        if cc not in nearest or (p.get('distance') or 1e9) < (nearest[cc].get('distance') or 1e9):
          nearest[cc] = p
      for c in missing:
        p = nearest.get(c['carrier_code'])
        if p:
          entry = {
            'point_code': p['code'], 'point_uuid': p['uuid'],
            'name': p.get('name'), 'address': p.get('address'),
            'distance_m': p.get('distance'),
          }
          cached[c['carrier_code']] = entry
          await vinted_store.save_pickup_pref(
            conn, user_id, c['carrier_code'], p['code'], p['uuid'],
            p.get('name'), p.get('address'), p.get('distance'),
          )

  # Candidates = item carriers that have a point (in cache).
  cands = []
  for c in carriers:
    pt = cached.get(c['carrier_code'])
    if pt:
      cands.append({**c, **pt})
  if not cands:
    return {'status': 'error', 'error': 'No pickup point available nearby'}

  within = [c for c in cands if _dist(c) <= max_distance_m]
  chosen = (
    min(within, key=_price) if within           # within threshold → the cheapest
    else min(cands, key=_dist)                   # none within threshold → the nearest
  )
  return {
    'status': 'ok',
    'rate_uuid':    chosen['rate_uuid'],
    'point_code':   chosen['point_code'],
    'point_uuid':   chosen['point_uuid'],
    'carrier_code': chosen['carrier_code'],
    'name':         chosen.get('name'),
    'address':      chosen.get('address'),
    'distance_m':   chosen.get('distance_m'),
    'price':        chosen.get('price'),
  }

"""
pickup_setup.py — helper for parsing the Vinted checkout response.

From a checkout's `components` (VintedSession.open_checkout / buy) it extracts:
  - shipping_order_id  (to call nearby_pickup_points at buy time)
  - the address postal code (to derive the coordinates)
  - pickup carriers available for that item (no home)
"""


def shipping_order_id(comps: dict):
  for k in ('shipping_pickup_options', 'shipping_pickup_details', 'shipping_address'):
    v = comps.get(k, {}).get('shipping_order_id')
    if v:
      return v
  return None


def postal_code(comps: dict):
  addr = (
    comps.get('shipping_pickup_details', {}).get('receiver_address')
    or comps.get('shipping_address', {}).get('address')
    or {}
  )
  return addr.get('postal_code')


def pickup_carriers(comps: dict) -> list[dict]:
  """PICKUP-type carriers available for the item (no home), with rate and price.
  The full list lives in shipping_pickup_details.pickup_types.pickup.shipping_options
  (pickup_types is a sibling of pickup_details, not a child)."""
  spd = comps.get('shipping_pickup_details', {})
  opts = spd.get('pickup_types', {}).get('pickup', {}).get('shipping_options')
  if not opts:  # fall back on alternative nestings
    opts = spd.get('pickup_details', {}).get('pickup_types', {}).get('pickup', {}).get('shipping_options')
  if not opts:
    opts = (
      comps.get('shipping_pickup_options', {})
           .get('pickup_types', {}).get('pickup', {})
           .get('shipping_options')
    ) or []
  out = []
  for o in opts:
    price = (o.get('receiver_final_price') or o.get('price') or {}).get('amount')
    out.append({
      'carrier_code': o.get('carrier_code'),
      'title':        o.get('title'),
      'rate_uuid':    o.get('rate_uuid'),
      'price':        price,
    })
  return out

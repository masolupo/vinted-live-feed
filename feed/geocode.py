"""
geocode.py — Italian postal code → coordinates (to center the pickup-point
search). Uses Nominatim (OpenStreetMap), free. In-memory cache: a postal code is
geocoded only once. Only needed while "breaking in" the points cache.
"""

import httpx

_cache: dict[str, tuple] = {}


async def cap_to_coords(cap: str | None, country: str = 'Italy') -> tuple | None:
  if not cap:
    return None
  if cap in _cache:
    return _cache[cap]
  try:
    async with httpx.AsyncClient(timeout=10, headers={'User-Agent': 'vlf/1.0'}) as cl:
      r = await cl.get(
        'https://nominatim.openstreetmap.org/search',
        params={'postalcode': cap, 'country': country, 'format': 'json', 'limit': 1},
      )
      data = r.json()
      if data:
        coords = (float(data[0]['lat']), float(data[0]['lon']))
        _cache[cap] = coords
        return coords
  except Exception:
    pass
  return None

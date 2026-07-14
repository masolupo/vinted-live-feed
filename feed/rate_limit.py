"""
rate_limit.py — in-process rate limiting (sliding window).

This is fine because the feed is a single process. Typical key: "<action>:<user_id>".
The per-IP rate limit on browser traffic (WS/filters) must be handled upstream
(reverse proxy) in deployment: at the feed, /vinted/* calls arrive from Next's IP.
"""

import time

# key → list of request timestamps in the window.
_hits: dict[str, list[float]] = {}


def allow(key: str, limit: int, window: float) -> bool:
  """True if the request is allowed (and records it), False if over the limit."""
  now = time.time()
  q = _hits.get(key)
  if q is None:
    q = []
    _hits[key] = q
  cutoff = now - window
  # discard the out-of-window timestamps (at the head)
  i = 0
  for t in q:
    if t >= cutoff:
      break
    i += 1
  if i:
    del q[:i]
  if len(q) >= limit:
    return False
  q.append(now)
  return True

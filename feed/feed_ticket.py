"""
feed_ticket.py — verification of the feed access "tickets" (WS + /filters).

The ticket is issued ONLY by the Next backend to authenticated users with an
active subscription, and it is short-lived. The feed verifies it to authorize
the WebSocket connection and the filter calls (see SECURITY_AUDIT.md VLF-01).

Format: "<uid>.<exp>.<sig>"
  - uid = user_id (Supabase UUID)
  - exp = expiry (unix seconds)
  - sig = HMAC-SHA256( "<uid>.<exp>", FEED_TICKET_SECRET ) in hex
Same scheme on the Next side (web/lib/feed-ticket): they must be kept in sync.
"""

import hashlib
import hmac
import time
from os import getenv


def _secret() -> str:
  return getenv('FEED_TICKET_SECRET', '')


def verify_ticket_full(token: str | None) -> tuple[str, int] | None:
  """Returns (user_id, exp) if the ticket is valid and not expired, otherwise None.
  `exp` is the expiry in unix seconds: it lets whoever keeps a long-lived
  connection open (WS) close it on expiry and force a re-check of the subscription."""
  secret = _secret()
  if not secret or not token:
    return None
  parts = token.split('.')
  if len(parts) != 3:
    return None
  uid, exp, sig = parts
  expected = hmac.new(secret.encode(), f'{uid}.{exp}'.encode(), hashlib.sha256).hexdigest()
  if not hmac.compare_digest(sig, expected):
    return None
  try:
    exp_i = int(exp)
  except ValueError:
    return None
  if exp_i < int(time.time()):
    return None
  return uid, exp_i


def verify_ticket(token: str | None) -> str | None:
  """Returns the user_id if the ticket is valid and not expired, otherwise None."""
  info = verify_ticket_full(token)
  return info[0] if info else None

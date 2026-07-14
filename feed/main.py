"""
main.py — VLF Feed (:5000). Vinted live feed engine.

Exposes:
  - WebSocket for the browser:
      WS   /ws      → live feed of Vinted items
  - REST:
      GET  /health
      GET  /filters/categories          → category tree (catalogTree)
      GET  /filters/colors              → colors
      GET  /filters/sizes               → size groups
      GET  /filters/conditions          → conditions
      GET  /filters/brands?q=<keyword>  → brand search

In-memory state:
  - connected_clients + client_connected: active WebSockets and a signal to
    suspend the fetch loop when there's no one listening.

Note: the whole "fast buy" part (login/2fa/refresh/buy/pickup) lives in `../vba`
and is NOT part of this service. See TODO.md.
"""

import asyncio
from contextlib import asynccontextmanager
from os import getenv

from dotenv import load_dotenv

# Load .env BEFORE the local imports: some modules (proxy_pool, etc.)
# may read environment variables at import time.
load_dotenv()

from urllib.parse import parse_qsl, urlencode

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

import feed_ticket
from pool_manager import PoolManager
from vinted_meta import VintedMeta
from vinted_api import router as vinted_router
import db
import refresh_worker


# Allowed origins for HTTP calls from the UI (CSV in env, default Next dev).
CORS_ORIGINS = getenv('CORS_ORIGINS', 'http://localhost:3000').split(',')


# ── Global state ──────────────────────────────────────────────────────────────

p_url = getenv('P_URL') or ''
# Base catalog/items (without querystring), to which the UI filters are appended.
base_url = p_url.split('?')[0]

# One pool of extractors per set of filters (see pool_manager.py).
manager = PoolManager(default_url=p_url, base_url=base_url)

# Source of the metadata for the filters (categories, brands, colors, sizes, conditions).
meta = VintedMeta()


# ── Lifespan: startup/shutdown of the service loops ───────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
  # Categories: static base from file, then a periodic refresh job (hybrid).
  meta.load_categories_from_file()
  categories_loop = asyncio.create_task(meta.categories_refresh_loop())

  # DB pool (proxy_pool / vinted_sessions for "Connect Vinted account").
  await db.init_pool()

  # Worker that keeps the Vinted sessions alive (refresh shortly before expiry).
  refresh_loop = asyncio.create_task(refresh_worker.refresh_loop())

  yield

  categories_loop.cancel()
  refresh_loop.cancel()
  await manager.shutdown()
  await meta.close()
  await db.close_pool()


app = FastAPI(title='VLF — Vinted Live Feed', lifespan=lifespan)

app.add_middleware(
  CORSMiddleware,
  allow_origins=CORS_ORIGINS,
  allow_methods=['GET'],
  allow_headers=['*'],
)

# /vinted/* endpoints (Vinted account login). Called only by the Next backend
# (server-to-server, no CORS) and protected by the internal secret.
app.include_router(vinted_router)


# Feed access (WS + filters): requires a valid ticket issued by Next only to
# subscribed users (anti paywall bypass + proxy abuse). See SECURITY_AUDIT VLF-01.
def _require_ticket(x_feed_ticket: str | None = Header(default=None)):
  if feed_ticket.verify_ticket(x_feed_ticket) is None:
    raise HTTPException(status_code=401, detail='feed ticket missing or invalid')


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get('/health')
async def health():
  # VLF-12: public liveness probe → status only, no pool/client counts
  # (the internal metrics stay available behind the signature, see /metrics).
  return {'status': 'ok'}


@app.get('/metrics', dependencies=[Depends(_require_ticket)])
async def metrics():
  return {'status': 'ok', **manager.stats()}


# ── Filters: metadata for the UI (require a ticket) ───────────────────────────

@app.get('/filters/categories', dependencies=[Depends(_require_ticket)])
async def filters_categories():
  """Category tree (catalogTree) for the cascading navigator."""
  return {'categories': meta.categories}


@app.get('/filters/colors', dependencies=[Depends(_require_ticket)])
async def filters_colors():
  return await meta.get_colors()


@app.get('/filters/sizes', dependencies=[Depends(_require_ticket)])
async def filters_sizes():
  return await meta.get_sizes()


@app.get('/filters/conditions', dependencies=[Depends(_require_ticket)])
async def filters_conditions():
  return await meta.get_conditions()


@app.get('/filters/brands', dependencies=[Depends(_require_ticket)])
async def filters_brands(q: str = ''):
  return await meta.search_brands(q)


# ── WebSocket: live feed ──────────────────────────────────────────────────────

@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
  """
  One connection = one client on the feed. The querystring (`/ws?ticket=..&<filters>`)
  determines the pool: the client receives only the items that match its
  filters. Requires a valid `ticket` (issued by Next to subscribers); the ticket
  is stripped from the query before deriving the pool key.
  """
  await ws.accept()
  pairs = parse_qsl(ws.scope.get('query_string', b'').decode(), keep_blank_values=False)
  ticket = next((v for k, v in pairs if k == 'ticket'), None)
  info = feed_ticket.verify_ticket_full(ticket)
  if info is None:
    await ws.close(code=4401)  # ticket missing/invalid
    return
  _uid, exp = info
  query = urlencode([(k, v) for k, v in pairs if k != 'ticket'])

  key = await manager.add_client(query, ws)
  if key is None:  # pool cap reached (anti-DoS)
    await ws.close(code=4503)
    return

  # Watchdog: the ticket is verified only at open time, but the connection lives a
  # long time. When the ticket expires we close the socket: the client reconnects
  # with a new ticket, which Next issues only if the subscription is still active
  # (so feed access is re-verified ~every TTL). See N-1.
  async def _ticket_watchdog():
    import time as _t
    await asyncio.sleep(max(0.0, exp - _t.time()))
    try:
      await ws.close(code=4401)  # ticket expired → force re-auth
    except Exception:
      pass

  wd = asyncio.create_task(_ticket_watchdog())
  try:
    async for _ in ws.iter_text():
      pass
  finally:
    wd.cancel()
    await manager.remove_client(key, ws)


if __name__ == '__main__':
  import uvicorn
  uvicorn.run(app, host='0.0.0.0', port=5000)

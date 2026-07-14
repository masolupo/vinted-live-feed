# VLF Feed — live feed engine

Python service (FastAPI) that scrapes the Vinted catalog through a pool of
rotating sessions and streams it to clients over WebSocket.

Extracted from `../../vba/apps/bot` (only the live feed part; the fast-buy stays in vba).

## Files

- `extractor.py` — `_Extractor` (single scraping session) + `ExtractorFactory`
  (rotating pool: one loop creates the extractors, one does the fetch and the broadcast).
- `main.py` — FastAPI app: WebSocket `/ws` (feed) + `GET /health`.

## Startup (dev)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in PROXY, C_URL, P_URL
.venv/bin/fastapi dev main.py --port 5000
```

## Status

See `../TODO.md`. In short, still missing: item deduplication, structured
parsing, per-user filters/pools, auth on `/ws`, logging, proxy scale management.

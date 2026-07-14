# VLF Web — interface

Next.js (App Router) frontend of the live feed. **No shadcn / external UI
libraries**: only hand-written reusable components + CSS Modules. Minimal.

## Structure

```
app/
  layout.tsx          — root layout + global styles
  page.tsx            — live feed page (client component)
  globals.css         — design tokens (colors, radii, spacing)
components/
  ui/                 — reusable base components
    Button.tsx
    Card.tsx
    Badge.tsx
  ItemCard.tsx        — card of a Vinted item
  ConnectionStatus.tsx — WS connection status
hooks/
  useFeed.ts          — WebSocket connection + dedup by id + reconnection
lib/
  types.ts            — VintedItem type + defensive parser for the Vinted JSON
```

## Getting started (dev)

```bash
cp .env.example .env.local   # point NEXT_PUBLIC_FEED_WS_URL at the Python feed
npm install
npm run dev                  # http://localhost:3000
```

Requires the feed engine (`../feed`) running on `ws://localhost:5000/ws`.

## Notes

- Images use a plain `<img>` (no `next/image`) to stay minimal.
- The feed sends the raw catalog API JSON: parsing/normalization all lives in
  `lib/types.ts`, so if the shape changes there's a single place to touch.

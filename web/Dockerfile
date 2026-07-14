# ── deps: install the dependencies ────────────────────────────────────────────
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

# ── builder: production build (standalone output) ─────────────────────────────
FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# WARNING: the NEXT_PUBLIC_* vars are "inlined" into the bundle at BUILD time, not at
# runtime. They must therefore be passed as build-args (see docker-compose.yml).
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_FEED_API_URL
ARG NEXT_PUBLIC_FEED_WS_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── runner: minimal final image ───────────────────────────────────────────────
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

# Standalone output: server.js + only the required modules.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]

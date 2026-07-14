-- vinted.sql — schema for "Link Vinted account" (fastbuy).
--
-- Two tables:
--   proxy_pool      → the dedicated BrightData IPs, one per row (1 IP = 1 user).
--   vinted_sessions → each user's Vinted session (tokens encrypted on the Python side).
--
-- Security: RLS enabled on both WITHOUT policies → no access from anon/authenticated
-- clients. Only the Python backend (postgres role, via DATABASE_URL) reads/writes.
-- The frontend asks the feed service API for the status, not the DB.
--
-- The sensitive values (access_token, refresh_token, cookies) are ENCRYPTED by
-- Python (Fernet) before they get here: nothing is ever stored in plaintext in the DB.

-- ── proxy_pool ───────────────────────────────────────────────────────────────
create table if not exists public.proxy_pool (
  id               uuid primary key default gen_random_uuid(),
  zone             text not null,                       -- e.g. 'isp_proxy6'
  ip               text not null unique,                -- dedicated IP pinned with -ip-
  status           text not null default 'free'
                     check (status in ('free', 'assigned', 'burned')),
  assigned_user_id uuid references auth.users (id) on delete set null,
  assigned_at      timestamptz,
  note             text,
  created_at       timestamptz not null default now()
);

-- One IP per user: blocks two rows assigned to the same user.
create unique index if not exists proxy_pool_one_per_user
  on public.proxy_pool (assigned_user_id)
  where assigned_user_id is not null;

alter table public.proxy_pool enable row level security;

-- ── vinted_sessions ──────────────────────────────────────────────────────────
create table if not exists public.vinted_sessions (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null unique references auth.users (id) on delete cascade,
  vinted_user_id     text,
  access_token       text,   -- encrypted (Fernet)
  refresh_token      text,   -- encrypted (Fernet)
  cookies            text,   -- encrypted (Fernet): JSON of the session cookies
  csrf               text,
  proxy_id           uuid references public.proxy_pool (id) on delete set null,
  status             text not null default 'active'
                       check (status in ('active', 'expired')),
  access_expires_at  timestamptz,
  refresh_expires_at timestamptz,
  last_refresh_at    timestamptz,
  -- User presence (heartbeat) and next scheduled access refresh (jitter).
  last_active_at     timestamptz,
  next_refresh_at    timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

-- Adds the columns if the table already existed (idempotent migration).
alter table public.vinted_sessions add column if not exists last_active_at  timestamptz;
alter table public.vinted_sessions add column if not exists next_refresh_at timestamptz;
-- VLF-11: the user's coordinates (from the postal code) geocoded ONLY ONCE and
-- reused, so Nominatim isn't queried on every warm-up of the points cache.
alter table public.vinted_sessions add column if not exists delivery_lat double precision;
alter table public.vinted_sessions add column if not exists delivery_lng double precision;

create index if not exists vinted_sessions_status on public.vinted_sessions (status);

alter table public.vinted_sessions enable row level security;

-- ── pickup_prefs: preferred pickup point per carrier, per user ────────────────
-- Maps {user, carrier} → the chosen physical point (stable). The rate_uuid is NOT
-- saved: it is per-order, and is re-fetched at purchase time.
create table if not exists public.pickup_prefs (
  user_id      uuid not null references auth.users (id) on delete cascade,
  carrier_code text not null,           -- e.g. INPOST-LOCKER-IT, BRT-SHOP-IT, POSTE-ITALIANE-SHOP
  point_code   text not null,
  point_uuid   text not null,
  name         text,
  address      text,
  distance_m   double precision,        -- distance from the point (cached for the choice)
  updated_at   timestamptz not null default now(),
  primary key (user_id, carrier_code)
);

alter table public.pickup_prefs add column if not exists distance_m double precision;

alter table public.pickup_prefs enable row level security;

-- ── buy_debug: NON-success payment responses (3DS, errors) for analysis ───────
-- Saves the full Vinted response when the payment is not 'success'
-- (e.g. 3DS / requires_action), so it can be studied later.
create table if not exists public.buy_debug (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid references auth.users (id) on delete set null,
  item_id        text,
  seller_id      text,
  payment_status text,
  result         jsonb,   -- full Vinted response (3DS detail, etc.)
  pickup         jsonb,   -- chosen carrier/point
  created_at     timestamptz not null default now()
);

alter table public.buy_debug enable row level security;

-- ── Seed proxy_pool: bring your own dedicated IPs (BYOP) ──────────────────────
-- Replace these example IPs (RFC 5737 documentation range) with your own
-- dedicated proxy IPs. The zone password lives in feed/.env (BRD_ZONE_PASSWORD).
insert into public.proxy_pool (zone, ip) values
  ('my_zone', '203.0.113.10'),
  ('my_zone', '203.0.113.11'),
  ('my_zone', '203.0.113.12')
on conflict (ip) do nothing;

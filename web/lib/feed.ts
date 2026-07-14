// Server-side helper to call the feed service (Python) on the internal
// /vinted/* endpoints. It SIGNS every request (HMAC) instead of sending a static
// bearer: the secret never travels over the wire. Use ONLY in route handlers.
// The scheme must stay aligned with feed/vinted_api.py (_verify_request).
import { createHmac } from 'crypto';

// INTERNAL feed URL (server→server, never from the browser): the /vinted/* calls
// must stay on the private network and NOT go through the public proxy, so they
// can be blocked from the outside by the reverse proxy. Default: localhost.
const FEED_URL =
  process.env.FEED_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_FEED_API_URL ??
  'http://localhost:5000';
const SECRET = process.env.FEED_INTERNAL_SECRET ?? '';

export async function feedFetch(path: string, init?: RequestInit) {
  const ts = Math.floor(Date.now() / 1000).toString();
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = typeof init?.body === 'string' ? init.body : '';
  // canonical: "<ts>.<METHOD>.<path?query>.<body>"
  const sig = createHmac('sha256', SECRET)
    .update(`${ts}.${method}.${path}.${body}`)
    .digest('hex');

  return fetch(`${FEED_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      'content-type': 'application/json',
      'x-feed-ts': ts,
      'x-feed-sig': sig,
    },
    cache: 'no-store',
  });
}

// Normalizes the feed response into { status?, error? } + the HTTP status to
// pass back to the client.
export async function feedJson(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { body: { error: data.detail ?? data.error ?? 'Service error' }, status: res.status };
  }
  return { body: data, status: 200 };
}

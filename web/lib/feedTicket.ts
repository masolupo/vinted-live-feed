// Client helper: fetches and caches the feed access ticket (WS + /filters).
// It requests it from /api/feed-ticket (authenticated + subscription) and reuses
// it while it's valid, renewing it when <30s remain before expiry.

let cached: { ticket: string; exp: number } | null = null;
let inflight: Promise<string | null> | null = null;

export async function getFeedTicket(): Promise<string | null> {
  const now = Date.now() / 1000;
  if (cached && cached.exp - now > 30) return cached.ticket;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const r = await fetch('/api/feed-ticket', { cache: 'no-store' });
      if (!r.ok) return null;
      const d = await r.json();
      if (d?.ticket && d?.exp) {
        cached = { ticket: d.ticket, exp: d.exp };
        return d.ticket as string;
      }
      return null;
    } catch {
      return null;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

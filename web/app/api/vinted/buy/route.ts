import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { hasActiveAccess } from '@/lib/access';
import { feedFetch } from '@/lib/feed';
import { csrfBlock } from '@/lib/csrf';

export const runtime = 'nodejs';

// Runs the fastbuy: the user buys the item using their connected Vinted
// session (the feed service handles token/proxy/purchase).
export async function POST(req: Request) {
  const blocked = csrfBlock(req);
  if (blocked) return blocked;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }
  if (!hasActiveAccess(user)) {
    return NextResponse.json({ error: 'Subscription not active' }, { status: 403 });
  }

  const { itemId, sellerId } = await req.json().catch(() => ({}));
  if (!itemId || !sellerId) {
    return NextResponse.json(
      { error: 'Incomplete item data (missing id or seller)' },
      { status: 400 },
    );
  }

  const res = await feedFetch('/vinted/buy', {
    method: 'POST',
    body: JSON.stringify({ user_id: user.id, item_id: String(itemId), seller_id: String(sellerId) }),
  });

  // The feed responds via STREAMING (NDJSON, one event per line): we forward it
  // as-is to the browser, which updates the button phase by phase.
  if (!res.ok || !res.body) {
    const d = await res.json().catch(() => ({}));
    return NextResponse.json(
      { error: d.detail ?? d.error ?? 'Service error' },
      { status: res.status || 502 },
    );
  }
  return new Response(res.body, {
    status: 200,
    headers: { 'content-type': 'application/x-ndjson', 'cache-control': 'no-store' },
  });
}

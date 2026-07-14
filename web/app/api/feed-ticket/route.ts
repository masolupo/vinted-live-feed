import { NextResponse } from 'next/server';
import { createHmac } from 'crypto';
import { createClient } from '@/utils/supabase/server';
import { hasActiveAccess } from '@/lib/access';

export const runtime = 'nodejs';

// Feed access ticket (WS + /filters): signed, short-lived, issued only to
// subscribed users. The Python feed verifies it (feed/feed_ticket.py).
// Format: "<uid>.<exp>.<HMAC-SHA256(<uid>.<exp>, FEED_TICKET_SECRET) hex>".
const SECRET = process.env.FEED_TICKET_SECRET ?? '';
const TTL_SEC = 600; // 10 minutes

export async function GET() {
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
  if (!SECRET) {
    return NextResponse.json({ error: 'FEED_TICKET_SECRET not configured' }, { status: 500 });
  }

  const exp = Math.floor(Date.now() / 1000) + TTL_SEC;
  const msg = `${user.id}.${exp}`;
  const sig = createHmac('sha256', SECRET).update(msg).digest('hex');
  return NextResponse.json({ ticket: `${msg}.${sig}`, exp });
}

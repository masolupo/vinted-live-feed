import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { hasActiveAccess } from '@/lib/access';
import { feedFetch, feedJson } from '@/lib/feed';
import { csrfBlock } from '@/lib/csrf';

export const runtime = 'nodejs';

// Starts the Vinted login for the logged-in user. Forwards credentials + user_id
// to the feed service, which assigns a dedicated IP and attempts to sign in.
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

  const { email, password } = await req.json().catch(() => ({}));
  if (!email || !password) {
    return NextResponse.json({ error: 'Vinted email and password required' }, { status: 400 });
  }

  const res = await feedFetch('/vinted/login', {
    method: 'POST',
    body: JSON.stringify({ user_id: user.id, email, password }),
  });
  const { body, status } = await feedJson(res);
  return NextResponse.json(body, { status });
}

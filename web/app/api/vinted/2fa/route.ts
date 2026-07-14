import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { hasActiveAccess } from '@/lib/access';
import { feedFetch, feedJson } from '@/lib/feed';
import { csrfBlock } from '@/lib/csrf';

export const runtime = 'nodejs';

// Completes the Vinted login by submitting the verification code (2FA) the
// user received via email.
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

  const { code } = await req.json().catch(() => ({}));
  if (!code) {
    return NextResponse.json({ error: 'Verification code required' }, { status: 400 });
  }

  const res = await feedFetch('/vinted/login/2fa', {
    method: 'POST',
    body: JSON.stringify({ user_id: user.id, code }),
  });
  const { body, status } = await feedJson(res);
  return NextResponse.json(body, { status });
}

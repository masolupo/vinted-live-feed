import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { feedFetch } from '@/lib/feed';
import { csrfBlock } from '@/lib/csrf';

export const runtime = 'nodejs';

// Presence heartbeat: while the user has VLS open, it tells the feed they are
// online → the worker keeps the access token fresh (refresh before the 2h mark).
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

  await feedFetch('/vinted/heartbeat', {
    method: 'POST',
    body: JSON.stringify({ user_id: user.id }),
  }).catch(() => {});

  return NextResponse.json({ ok: true });
}

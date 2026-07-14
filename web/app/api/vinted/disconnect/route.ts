import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { feedFetch, feedJson } from '@/lib/feed';
import { csrfBlock } from '@/lib/csrf';

export const runtime = 'nodejs';

// Disconnects the Vinted account: removes the session and frees the dedicated IP.
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

  const res = await feedFetch(`/vinted/session?user_id=${user.id}`, {
    method: 'DELETE',
  });
  const { body, status } = await feedJson(res);
  return NextResponse.json(body, { status });
}

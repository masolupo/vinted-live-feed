import { NextResponse } from 'next/server';
import { createClient } from '@/utils/supabase/server';
import { feedFetch, feedJson } from '@/lib/feed';

export const runtime = 'nodejs';

// Status of the user's Vinted connection: 'connected' | 'expired' | 'none'.
export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  const res = await feedFetch(`/vinted/status?user_id=${user.id}`);
  const { body, status } = await feedJson(res);
  return NextResponse.json(body, { status });
}

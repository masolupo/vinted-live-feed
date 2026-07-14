import { createClient } from '@supabase/supabase-js';

// Supabase client with admin privileges (SECRET key): used ONLY server-side,
// e.g. for server-side operations that need to bypass RLS.
// Does not use/persist user sessions.
export const createAdminClient = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SECRET_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );

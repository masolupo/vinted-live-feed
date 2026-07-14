import { createBrowserClient } from '@supabase/ssr';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

// Supabase client for browser-side components ('use client').
export const createClient = () => createBrowserClient(supabaseUrl, supabaseKey);

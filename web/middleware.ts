import { type NextRequest } from 'next/server';
import { updateSession } from '@/utils/supabase/middleware';

// Next middleware: keeps the Supabase session alive/refreshed on every
// request (except static assets and images).
export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    // Excludes /api (routes handle auth themselves) and static assets.
    '/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};

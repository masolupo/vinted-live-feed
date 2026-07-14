import { NextResponse } from 'next/server';

// CSRF defense for MUTATING route handlers (POST/DELETE): rejects requests from
// an origin other than the app's. Browsers always include the `Origin` header on
// "unsafe" requests (even cross-site), so if it's present and doesn't match the
// app it's (likely) CSRF. It's a defense in depth on top of the SameSite of the
// Supabase session cookie. See SECURITY_AUDIT VLF-06.

const APP_ORIGIN = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000').origin;
  } catch {
    return 'http://localhost:3000';
  }
})();

/** Returns a 403 if the request is cross-site, otherwise null (proceed). */
export function csrfBlock(req: Request): NextResponse | null {
  const origin = req.headers.get('origin');
  if (origin && origin !== APP_ORIGIN) {
    return NextResponse.json({ error: 'Origin not allowed' }, { status: 403 });
  }
  return null;
}

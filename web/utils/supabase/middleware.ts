import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

// Refreshes the Supabase session AND applies the access "gate".
// Public routes (visible even when logged out): "/" (landing) and "/login".
//   - not logged in on a private route → /login
//   - logged in                        → app (/feed)
export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value),
        );
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options),
        );
      },
    },
  });

  // IMPORTANT: do not insert code between createServerClient and getUser().
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isLanding = path === '/';
  const isLogin = path === '/login';
  const isPublic = isLanding || isLogin;

  // Redirect that preserves any updated session cookies.
  const redirect = (to: string) => {
    const url = request.nextUrl.clone();
    url.pathname = to;
    url.search = '';
    const res = NextResponse.redirect(url);
    supabaseResponse.cookies.getAll().forEach((c) => res.cookies.set(c));
    return res;
  };

  if (!user) {
    // Logged out: can only see the public routes, everything else → /login.
    return isPublic ? supabaseResponse : redirect('/login');
  }

  // Logged in: no landing/login, send them to the app.
  if (isLanding || isLogin) return redirect('/feed');

  return supabaseResponse;
}

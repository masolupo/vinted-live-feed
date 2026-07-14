import type { User } from '@supabase/supabase-js';

/**
 * Access control. This open-source build has NO paywall: every authenticated
 * user has access. (The original product gated access behind a Stripe
 * subscription; that logic and its wiring have been removed from this public
 * version.)
 */
export function hasActiveAccess(user: User | null): boolean {
  return !!user;
}

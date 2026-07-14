'use server';

import { createClient } from '@/utils/supabase/server';

// Password requirements validated SERVER-SIDE (authoritative). Keep the same
// ones in the Supabase password policy to cover direct API calls.
function validatePassword(pw: string): string | null {
  if (pw.length < 8) return 'Password must be at least 8 characters long.';
  if (!/[A-Z]/.test(pw)) return 'At least one uppercase letter is required.';
  if (!/[0-9]/.test(pw)) return 'At least one number is required.';
  if (!/[^A-Za-z0-9]/.test(pw)) return 'At least one special character is required.';
  return null;
}

export interface SignUpResult {
  error?: string;
  needsConfirm?: boolean;
}

export async function signUpAction(
  email: string,
  password: string,
  confirm: string,
): Promise<SignUpResult> {
  const pwError = validatePassword(password);
  if (pwError) return { error: pwError };
  if (password !== confirm) return { error: 'The passwords do not match.' };

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) return { error: error.message };

  // If email confirmation is enabled, there is no session: the user must confirm.
  return { needsConfirm: !data.session };
}

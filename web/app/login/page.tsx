'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/utils/supabase/client';
import { signUpAction } from './actions';
import { Button } from '@/components/ui/Button';
import styles from '../auth.module.css';

export default function LoginPage() {
  const router = useRouter();
  const supabase = createClient();

  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Lightweight client-side check for instant feedback; the authoritative one is
  // in the Server Action (signUpAction).
  const validatePassword = (pw: string): string | null => {
    if (pw.length < 8) return 'Password must be at least 8 characters long.';
    if (!/[A-Z]/.test(pw)) return 'At least one uppercase letter is required.';
    if (!/[0-9]/.test(pw)) return 'At least one number is required.';
    if (!/[^A-Za-z0-9]/.test(pw)) return 'At least one special character is required.';
    return null;
  };

  const switchMode = (m: 'login' | 'signup') => {
    setMode(m);
    setError(null);
    setNote(null);
    setConfirm('');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNote(null);

    // Instant feedback (the real validation is server-side).
    if (mode === 'signup') {
      const pwError = validatePassword(password);
      if (pwError) return setError(pwError);
      if (password !== confirm) return setError('The passwords do not match.');
    }

    setLoading(true);

    if (mode === 'signup') {
      // Sign-up via Server Action: validates the password on our server.
      const res = await signUpAction(email, password, confirm);
      setLoading(false);
      if (res.error) return setError(res.error);
      if (res.needsConfirm) {
        return setNote('We\'ve sent you a confirmation email. Open it to activate your account.');
      }
    } else {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      setLoading(false);
      if (error) return setError(error.message);
    }

    // Session created: go to the app; the middleware redirects to the paywall if
    // the subscription is not active yet.
    router.push('/feed');
    router.refresh();
  };

  return (
    <div className={styles.screen}>
      <div className={styles.card}>
        <h1 className={styles.brand}>Blim</h1>
        <p className={styles.sub}>
          {mode === 'login' ? 'Sign in to your account.' : 'Create an account to get started.'}
        </p>

        <form className={styles.form} onSubmit={submit}>
          <input
            className={styles.input}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <input
            className={styles.input}
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          {mode === 'signup' && (
            <>
              <input
                className={styles.input}
                type="password"
                placeholder="Confirm password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                autoComplete="new-password"
              />
              <p className={styles.note}>
                At least 8 characters, with an uppercase letter, a number and a
                special character.
              </p>
            </>
          )}

          {error && <p className={styles.error}>{error}</p>}
          {note && <p className={styles.note}>{note}</p>}

          <Button type="submit" disabled={loading}>
            {loading
              ? 'Please wait…'
              : mode === 'login'
                ? 'Sign in'
                : 'Sign up'}
          </Button>
        </form>

        <div className={styles.switch}>
          {mode === 'login' ? (
            <>
              Don&apos;t have an account?{' '}
              <button
                type="button"
                className={styles.link}
                onClick={() => switchMode('signup')}
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <button
                type="button"
                className={styles.link}
                onClick={() => switchMode('login')}
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

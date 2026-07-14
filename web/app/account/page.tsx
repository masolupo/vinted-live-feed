'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/Button';
import { getInstantBuy, setInstantBuy } from '@/lib/prefs';
import authStyles from '../auth.module.css';
import styles from './account.module.css';

type Status = 'loading' | 'none' | 'connected' | 'expired';

export default function AccountPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>('loading');
  const [stage, setStage] = useState<'form' | '2fa'>('form');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Local preference: instant fastbuy (skips the confirmation).
  const [instant, setInstant] = useState(false);
  useEffect(() => setInstant(getInstantBuy()), []);
  const toggleInstant = () => {
    const v = !instant;
    setInstantBuy(v);
    setInstant(v);
  };

  const loadStatus = () => {
    fetch('/api/vinted/status')
      .then((r) => (r.ok ? r.json() : { status: 'none' }))
      .then((d) => setStatus(d.status ?? 'none'))
      .catch(() => setStatus('none'));
  };
  useEffect(loadStatus, []);

  // Step 1: submit the credentials. Outcomes: connected | 2FA needed | error.
  const connect = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      const res = await fetch('/api/vinted/connect', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const d = await res.json().catch(() => ({}));
      if (d.status === 'connected') {
        setStatus('connected');
        setStage('form');
        setPassword('');
      } else if (d.status === '2fa_required') {
        setStage('2fa');
        setInfo('Vinted has sent you a code by email. Enter it below.');
      } else {
        setError(d.error ?? 'Sign-in failed.');
      }
    } catch {
      setError('Network error. Try again.');
    }
    setBusy(false);
  };

  // Step 2: submit the verification code received by email.
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await fetch('/api/vinted/2fa', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const d = await res.json().catch(() => ({}));
      if (d.status === 'connected') {
        setStatus('connected');
        setStage('form');
        setPassword('');
        setCode('');
      } else {
        setError(d.error ?? 'Invalid code. Please sign in again.');
        setStage('form');
        setCode('');
      }
    } catch {
      setError('Network error. Try again.');
    }
    setBusy(false);
  };

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await fetch('/api/vinted/disconnect', { method: 'POST' });
      setStatus('none');
      setStage('form');
      setEmail('');
      setPassword('');
    } catch {
      setError('Could not disconnect. Try again.');
    }
    setBusy(false);
  };

  return (
    <div className={authStyles.screen}>
      <div className={authStyles.card}>
        <h1 className={authStyles.brand}>Vinted account</h1>
        <p className={authStyles.sub}>
          Connect your Vinted account to use fastbuy: we buy for you in
          seconds straight from the feed.
        </p>

        <div className={styles.statusRow}>
          <span className={`${styles.badge} ${styles[status === 'loading' ? 'none' : status]}`}>
            {status === 'loading' && '…'}
            {status === 'connected' && '● Connected'}
            {status === 'expired' && '● Session expired'}
            {status === 'none' && '○ Not connected'}
          </span>
        </div>

        {status === 'connected' ? (
          <>
            <p className={authStyles.note}>Your account is connected.</p>

            <label className={styles.toggle}>
              <input type="checkbox" checked={instant} onChange={toggleInstant} />
              <span>Instant buy — skip the Fastbuy confirmation</span>
            </label>
            {instant && (
              <p className={authStyles.note}>
                ⚠️ Fastbuy will buy on the first click, without asking for confirmation.
              </p>
            )}

            <div className={styles.actions}>
              <Button variant="ghost" onClick={disconnect} disabled={busy}>
                {busy ? 'Please wait…' : 'Disconnect account'}
              </Button>
            </div>
          </>
        ) : stage === 'form' ? (
          <form className={authStyles.form} onSubmit={connect}>
            <input
              className={authStyles.input}
              type="email"
              placeholder="Vinted email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="off"
            />
            <input
              className={authStyles.input}
              type="password"
              placeholder="Vinted password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="off"
            />
            {error && <p className={authStyles.error}>{error}</p>}
            <Button type="submit" disabled={busy}>
              {busy ? 'Connecting…' : 'Connect account'}
            </Button>
          </form>
        ) : (
          <form className={authStyles.form} onSubmit={verify}>
            {info && <p className={authStyles.note}>{info}</p>}
            <input
              className={authStyles.input}
              type="text"
              inputMode="numeric"
              placeholder="Verification code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoFocus
              autoComplete="one-time-code"
            />
            {error && <p className={authStyles.error}>{error}</p>}
            <Button type="submit" disabled={busy}>
              {busy ? 'Verifying…' : 'Confirm code'}
            </Button>
            <button
              type="button"
              className={authStyles.link}
              onClick={() => {
                setStage('form');
                setCode('');
                setError(null);
                setInfo(null);
              }}
            >
              Cancel
            </button>
          </form>
        )}

        <div className={styles.back}>
          <button type="button" className={authStyles.link} onClick={() => router.push('/feed')}>
            ← Back to feed
          </button>
        </div>
      </div>
    </div>
  );
}

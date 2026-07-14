'use client';

import styles from './PriceRange.module.css';

interface Props {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}

export function PriceRange({ from, to, onChange }: Props) {
  // Solo cifre (e vuoto), niente segni.
  const clean = (v: string) => v.replace(/[^0-9]/g, '');

  return (
    <div className={styles.row}>
      <input
        className={styles.input}
        type="number"
        min="0"
        inputMode="numeric"
        placeholder="Min €"
        value={from}
        onChange={(e) => onChange(clean(e.target.value), to)}
      />
      <span className={styles.sep}>–</span>
      <input
        className={styles.input}
        type="number"
        min="0"
        inputMode="numeric"
        placeholder="Max €"
        value={to}
        onChange={(e) => onChange(from, clean(e.target.value))}
      />
    </div>
  );
}

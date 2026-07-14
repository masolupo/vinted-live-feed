'use client';

import { useState, type ReactNode } from 'react';
import styles from './Section.module.css';

interface Props {
  title: string;
  defaultOpen?: boolean;
  hint?: string;
  children: ReactNode;
}

export function Section({ title, defaultOpen = false, hint, children }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={styles.section}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={styles.title}>{title}</span>
        <span className={styles.right}>
          {hint && <span className={styles.hint}>{hint}</span>}
          <span className={styles.arrow}>{open ? '−' : '+'}</span>
        </span>
      </button>
      {open && <div className={styles.body}>{children}</div>}
    </div>
  );
}

import type { HTMLAttributes } from 'react';
import styles from './Badge.module.css';

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  const cls = [styles.badge, className].filter(Boolean).join(' ');
  return <span className={cls} {...props} />;
}

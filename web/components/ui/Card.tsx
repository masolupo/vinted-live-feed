import type { HTMLAttributes } from 'react';
import styles from './Card.module.css';

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  const cls = [styles.card, className].filter(Boolean).join(' ');
  return <div className={cls} {...props} />;
}

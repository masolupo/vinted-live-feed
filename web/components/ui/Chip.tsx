import type { ButtonHTMLAttributes } from 'react';
import styles from './Chip.module.css';

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
}

export function Chip({ selected = false, className, ...props }: ChipProps) {
  const cls = [styles.chip, selected ? styles.selected : '', className]
    .filter(Boolean)
    .join(' ');
  return <button type="button" className={cls} {...props} />;
}

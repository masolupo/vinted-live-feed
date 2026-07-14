'use client';

import type { Color } from '@/lib/filters';
import styles from './ColorPicker.module.css';

interface Props {
  colors: Color[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}

export function ColorPicker({ colors, selectedIds, onChange }: Props) {
  const toggle = (id: number) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );
  };

  return (
    <div className={styles.grid}>
      {colors.map((c) => {
        const sel = selectedIds.includes(c.id);
        return (
          <button
            key={c.id}
            type="button"
            title={c.title}
            aria-label={c.title}
            className={`${styles.swatch} ${sel ? styles.selected : ''}`}
            style={{ background: `#${c.hex}` }}
            onClick={() => toggle(c.id)}
          />
        );
      })}
    </div>
  );
}

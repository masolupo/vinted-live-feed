'use client';

import type { Status } from '@/lib/filters';
import { Chip } from '@/components/ui/Chip';
import styles from './ConditionPicker.module.css';

interface Props {
  statuses: Status[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}

export function ConditionPicker({ statuses, selectedIds, onChange }: Props) {
  const toggle = (id: number) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );
  };

  return (
    <div className={styles.chips}>
      {statuses.map((s) => (
        <Chip
          key={s.id}
          selected={selectedIds.includes(s.id)}
          onClick={() => toggle(s.id)}
        >
          {s.title}
        </Chip>
      ))}
    </div>
  );
}

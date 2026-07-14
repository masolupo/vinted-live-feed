'use client';

import { useState } from 'react';
import type { SizeGroup } from '@/lib/filters';
import { Chip } from '@/components/ui/Chip';
import styles from './SizePicker.module.css';

interface Props {
  groups: SizeGroup[];
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}

export function SizePicker({ groups, selectedIds, onChange }: Props) {
  // Only groups that have a caption and sizes.
  const usable = groups.filter((g) => g.caption && g.sizes.length > 0);
  const [groupId, setGroupId] = useState<number | null>(
    usable.length ? usable[0].id : null,
  );
  const group = usable.find((g) => g.id === groupId) ?? null;

  const toggle = (id: number) => {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );
  };

  if (!usable.length) return <div className={styles.hint}>no sizes</div>;

  return (
    <div className={styles.wrap}>
      <select
        className={styles.select}
        value={groupId ?? ''}
        onChange={(e) => setGroupId(Number(e.target.value))}
      >
        {usable.map((g) => (
          <option key={g.id} value={g.id}>
            {g.caption}
          </option>
        ))}
      </select>

      {group && (
        <div className={styles.chips}>
          {group.sizes.map((s) => (
            <Chip
              key={s.id}
              selected={selectedIds.includes(s.id)}
              onClick={() => toggle(s.id)}
            >
              {s.title}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

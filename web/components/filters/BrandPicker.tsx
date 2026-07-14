'use client';

import { useEffect, useRef, useState } from 'react';
import { fetchBrands } from '@/lib/api';
import type { Brand } from '@/lib/filters';
import { Chip } from '@/components/ui/Chip';
import styles from './BrandPicker.module.css';

interface Props {
  selected: Brand[];
  onChange: (brands: Brand[]) => void;
}

export function BrandPicker({ selected, onChange }: Props) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    debounce.current = setTimeout(async () => {
      try {
        const { brands } = await fetchBrands(q.trim());
        setResults(brands);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [q]);

  const toggle = (b: Brand) => {
    const has = selected.some((s) => s.id === b.id);
    onChange(has ? selected.filter((s) => s.id !== b.id) : [...selected, b]);
  };

  return (
    <div className={styles.wrap}>
      {selected.length > 0 && (
        <div className={styles.chips}>
          {selected.map((b) => (
            <Chip key={b.id} selected onClick={() => toggle(b)}>
              {b.title} ✕
            </Chip>
          ))}
        </div>
      )}

      <input
        className={styles.input}
        type="text"
        placeholder="Search for a brand…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      {loading && <div className={styles.hint}>searching…</div>}

      {results.length > 0 && (
        <ul className={styles.results}>
          {results.map((b) => {
            const isSel = selected.some((s) => s.id === b.id);
            return (
              <li key={b.id}>
                <button
                  type="button"
                  className={`${styles.result} ${isSel ? styles.resultSel : ''}`}
                  onClick={() => toggle(b)}
                >
                  {b.title}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

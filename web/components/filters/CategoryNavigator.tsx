'use client';

import { useState } from 'react';
import type { Category } from '@/lib/filters';
import styles from './CategoryNavigator.module.css';

interface Props {
  roots: Category[];
  value: Category | null;
  // Receives the chosen category and the full path (root → leaf).
  onChange: (cat: Category | null, path: Category[]) => void;
}

/**
 * Cascading category navigator like Vinted: you start from the top levels
 * (Women, Men, …), click to reveal subcategories, and build the search one
 * step at a time. The breadcrumb lets you go back up.
 */
export function CategoryNavigator({ roots, value, onChange }: Props) {
  // Currently open drill-down path (ancestors).
  const [stack, setStack] = useState<Category[]>([]);

  const current = stack.length ? stack[stack.length - 1] : null;
  const children = current ? current.catalogs : roots;

  const open = (cat: Category) => {
    // selecting = filter by this category; the path is the currently open
    // ancestors (stack) plus the clicked category.
    onChange(cat, [...stack, cat]);
    if (cat.catalogs.length) setStack([...stack, cat]);
  };

  // Click on a breadcrumb crumb: go back to that level.
  const goTo = (index: number) => {
    if (index < 0) {
      setStack([]);
      onChange(null, []);
    } else {
      const next = stack.slice(0, index + 1);
      setStack(next);
      onChange(next[next.length - 1], next);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.breadcrumb}>
        <button type="button" className={styles.crumb} onClick={() => goTo(-1)}>
          All
        </button>
        {stack.map((c, i) => (
          <span key={c.id} className={styles.crumbGroup}>
            <span className={styles.sep}>/</span>
            <button
              type="button"
              className={styles.crumb}
              onClick={() => goTo(i)}
            >
              {c.title}
            </button>
          </span>
        ))}
      </div>

      <ul className={styles.list}>
        {children.map((cat) => {
          const selected = value?.id === cat.id;
          const hasKids = cat.catalogs.length > 0;
          return (
            <li key={cat.id}>
              <button
                type="button"
                className={`${styles.row} ${selected ? styles.rowSelected : ''}`}
                onClick={() => open(cat)}
              >
                <span>{cat.title}</span>
                {hasKids && <span className={styles.chevron}>›</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

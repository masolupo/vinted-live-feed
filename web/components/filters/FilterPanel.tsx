'use client';

import { useEffect, useState } from 'react';
import {
  fetchCategories,
  fetchColors,
  fetchConditions,
  fetchSizes,
} from '@/lib/api';
import {
  emptySelection,
  countActiveFilters,
  type Brand,
  type Category,
  type Color,
  type SizeGroup,
  type Status,
  type FilterSelection,
} from '@/lib/filters';
import { Button } from '@/components/ui/Button';
import { Section } from '@/components/ui/Section';
import { CategoryNavigator } from './CategoryNavigator';
import { BrandPicker } from './BrandPicker';
import { ColorPicker } from './ColorPicker';
import { SizePicker } from './SizePicker';
import { ConditionPicker } from './ConditionPicker';
import { PriceRange } from './PriceRange';
import styles from './FilterPanel.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
  onApply: (sel: FilterSelection) => void;
}

export function FilterPanel({ open, onClose, onApply }: Props) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [colors, setColors] = useState<Color[]>([]);
  const [sizeGroups, setSizeGroups] = useState<SizeGroup[]>([]);
  const [statuses, setStatuses] = useState<Status[]>([]);

  const [sel, setSel] = useState<FilterSelection>(emptySelection);
  const set = (patch: Partial<FilterSelection>) =>
    setSel((s) => ({ ...s, ...patch }));

  // Load the metadata once. Categories are instant (static);
  // colors/sizes/conditions come live from the backend.
  useEffect(() => {
    fetchCategories().then((d) => setCategories(d.categories)).catch(() => {});
    fetchColors().then((d) => setColors(d.colors)).catch(() => {});
    fetchSizes().then((d) => setSizeGroups(d.size_groups)).catch(() => {});
    fetchConditions().then((d) => setStatuses(d.statuses)).catch(() => {});
  }, []);

  const active = countActiveFilters(sel);
  const hint = (n: number) => (n ? String(n) : undefined);

  return (
    <>
      <div
        className={`${styles.backdrop} ${open ? styles.backdropOpen : ''}`}
        onClick={onClose}
      />
      <aside
        className={`${styles.panel} ${open ? styles.panelOpen : ''} prettyScroll`}
        aria-hidden={!open}
      >
        <div className={styles.head}>
          <span className={styles.headTitle}>Filters</span>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close filters"
          >
            ✕
          </button>
        </div>

        <div className={styles.keyword}>
          <label className={styles.keywordLabel}>Product / keywords</label>
          <input
            className={styles.keywordInput}
            type="text"
            placeholder="e.g. Nike Air Max 90"
            value={sel.searchText}
            onChange={(e) => set({ searchText: e.target.value })}
          />
        </div>

        <Section title="Category" defaultOpen hint={sel.category?.title}>
          <CategoryNavigator
            roots={categories}
            value={sel.category}
            onChange={(category, categoryPath) => set({ category, categoryPath })}
          />
        </Section>

        <Section title="Brand" hint={hint(sel.brands.length)}>
          <BrandPicker
            selected={sel.brands}
            onChange={(brands: Brand[]) => set({ brands })}
          />
        </Section>

        <Section title="Price">
          <PriceRange
            from={sel.priceFrom}
            to={sel.priceTo}
            onChange={(priceFrom, priceTo) => set({ priceFrom, priceTo })}
          />
        </Section>

        <Section title="Size" hint={hint(sel.sizeIds.length)}>
          <SizePicker
            groups={sizeGroups}
            selectedIds={sel.sizeIds}
            onChange={(sizeIds) => set({ sizeIds })}
          />
        </Section>

        <Section title="Color" hint={hint(sel.colorIds.length)}>
          <ColorPicker
            colors={colors}
            selectedIds={sel.colorIds}
            onChange={(colorIds) => set({ colorIds })}
          />
        </Section>

        <Section title="Condition" hint={hint(sel.statusIds.length)}>
          <ConditionPicker
            statuses={statuses}
            selectedIds={sel.statusIds}
            onChange={(statusIds) => set({ statusIds })}
          />
        </Section>

        <div className={styles.actions}>
          <Button
            onClick={() => {
              onApply(sel);
              onClose();
            }}
          >
            Apply{active ? ` (${active})` : ''}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setSel(emptySelection);
              onApply(emptySelection);
            }}
          >
            Reset
          </Button>
        </div>
      </aside>
    </>
  );
}

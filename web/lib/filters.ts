// ── Filter metadata types (actual shape of the backend endpoints) ─────────────

export interface Category {
  id: number;
  title: string;
  code: string | null;
  catalogs: Category[];
}

export interface Color {
  id: number;
  title: string;
  hex: string;
}

export interface Status {
  id: number;
  title: string;
}

export interface Size {
  id: number;
  title: string;
}

export interface SizeGroup {
  id: number;
  caption: string | null;
  sizes: Size[];
}

export interface Brand {
  id: number;
  title: string;
}

// ── Filter selection made by the user ─────────────────────────────────────────

export interface FilterSelection {
  searchText: string; // keywords: the exact product (e.g. "nike air max 90")
  category: Category | null;
  categoryPath: Category[]; // drill-down breadcrumb
  brands: Brand[];
  sizeIds: number[];
  colorIds: number[];
  statusIds: number[];
  priceFrom: string;
  priceTo: string;
}

export const emptySelection: FilterSelection = {
  searchText: '',
  category: null,
  categoryPath: [],
  brands: [],
  sizeIds: [],
  colorIds: [],
  statusIds: [],
  priceFrom: '',
  priceTo: '',
};

// It's a live feed: the order is always "newest first".
const ORDER = 'newest_first';
const CURRENCY = 'EUR';

/**
 * Builds the query string for /api/v2/catalog/items from the selection.
 * Parameters verified live against Vinted (see backend).
 */
export function buildFeedQuery(sel: FilterSelection): string {
  const p = new URLSearchParams();
  p.set('order', ORDER);

  if (sel.searchText.trim()) p.set('search_text', sel.searchText.trim());
  if (sel.category) p.set('catalog_ids', String(sel.category.id));
  if (sel.brands.length) p.set('brand_ids', sel.brands.map((b) => b.id).join(','));
  if (sel.sizeIds.length) p.set('size_ids', sel.sizeIds.join(','));
  if (sel.colorIds.length) p.set('color_ids', sel.colorIds.join(','));
  if (sel.statusIds.length) p.set('status_ids', sel.statusIds.join(','));
  if (sel.priceFrom) {
    p.set('price_from', sel.priceFrom);
    p.set('currency', CURRENCY);
  }
  if (sel.priceTo) {
    p.set('price_to', sel.priceTo);
    p.set('currency', CURRENCY);
  }
  return p.toString();
}

/** Human-readable summary of the active filters, e.g. "Electronics › Video games · Nike". */
export function buildSummary(sel: FilterSelection): string {
  const parts: string[] = [];

  if (sel.searchText.trim()) parts.push(`"${sel.searchText.trim()}"`);

  if (sel.categoryPath.length) {
    parts.push(sel.categoryPath.map((c) => c.title).join(' › '));
  } else if (sel.category) {
    parts.push(sel.category.title);
  }

  if (sel.brands.length) parts.push(sel.brands.map((b) => b.title).join(', '));

  if (sel.priceFrom && sel.priceTo) parts.push(`${sel.priceFrom}–${sel.priceTo} €`);
  else if (sel.priceFrom) parts.push(`from ${sel.priceFrom} €`);
  else if (sel.priceTo) parts.push(`up to ${sel.priceTo} €`);

  if (sel.sizeIds.length) parts.push(`${sel.sizeIds.length} sizes`);
  if (sel.colorIds.length) parts.push(`${sel.colorIds.length} colors`);
  if (sel.statusIds.length) parts.push(`${sel.statusIds.length} conditions`);

  return parts.join('  ·  ');
}

/** Number of active filters (for badge/UX). */
export function countActiveFilters(sel: FilterSelection): number {
  return (
    (sel.searchText.trim() ? 1 : 0) +
    (sel.category ? 1 : 0) +
    sel.brands.length +
    sel.sizeIds.length +
    sel.colorIds.length +
    sel.statusIds.length +
    (sel.priceFrom ? 1 : 0) +
    (sel.priceTo ? 1 : 0)
  );
}

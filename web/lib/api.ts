import type { Category, Color, Status, SizeGroup, Brand } from './filters';
import { getFeedTicket } from './feedTicket';

const API_BASE =
  process.env.NEXT_PUBLIC_FEED_API_URL ?? 'http://localhost:5000';

async function getJson<T>(path: string): Promise<T> {
  const ticket = await getFeedTicket();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: ticket ? { 'x-feed-ticket': ticket } : {},
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export function fetchCategories(): Promise<{ categories: Category[] }> {
  return getJson('/filters/categories');
}

export function fetchColors(): Promise<{ colors: Color[] }> {
  return getJson('/filters/colors');
}

export function fetchConditions(): Promise<{ statuses: Status[] }> {
  return getJson('/filters/conditions');
}

export function fetchSizes(): Promise<{ size_groups: SizeGroup[] }> {
  return getJson('/filters/sizes');
}

export function fetchBrands(q: string): Promise<{ brands: Brand[] }> {
  return getJson(`/filters/brands?q=${encodeURIComponent(q)}`);
}

// A photo of the item: large url (for the main view) + small thumb.
export interface VintedPhoto {
  url: string;    // large image
  thumb: string;  // small version for the little squares
}

// Minimal, normalized shape of a Vinted item, independent of the raw JSON.
export interface VintedItem {
  id: string;
  title: string;
  price: string | null;     // e.g. "12,00 €"
  brand: string | null;
  size: string | null;
  photos: VintedPhoto[];    // [0] is the main one; empty if no photos
  url: string | null;       // link to the listing
  sellerId: string | null;  // seller id (for fastbuy)
}

// Extracts a readable price from one of the many shapes Vinted uses.
function parsePrice(raw: any): string | null {
  const p = raw?.price ?? raw?.total_item_price;
  if (p == null) return null;
  if (typeof p === 'string' || typeof p === 'number') return String(p);
  // { amount, currency_code } shape
  if (typeof p === 'object' && p.amount != null) {
    const cur = p.currency_code === 'EUR' ? '€' : (p.currency_code ?? '');
    return `${p.amount} ${cur}`.trim();
  }
  return null;
}

// Picks a "small" thumbnail among those available; falls back to the full url.
function pickThumb(p: any): string {
  const thumbs: any[] = p?.thumbnails ?? [];
  const byType = (t: string) => thumbs.find((x) => x?.type === t)?.url;
  return (
    byType('thumb150x210') ??
    byType('thumb70x100') ??
    byType('thumb310x430') ??
    thumbs[0]?.url ??
    p?.url ??
    ''
  );
}

// Normalizes a single raw photo into { url, thumb }. null if it has no url.
function normalizePhoto(p: any): VintedPhoto | null {
  const url = p?.url;
  if (!url) return null;
  return { url, thumb: pickThumb(p) || url };
}

// Extracts the item's photo list (main one first).
function parsePhotos(raw: any): VintedPhoto[] {
  const list: any[] = Array.isArray(raw?.photos) ? raw.photos : [];
  const out: VintedPhoto[] = [];
  for (const p of list) {
    const photo = normalizePhoto(p);
    if (photo) out.push(photo);
  }
  // Fallback: single `photo` field if the array is missing.
  if (out.length === 0) {
    const single = normalizePhoto(raw?.photo);
    if (single) out.push(single);
  }
  return out;
}

// Normalizes a single raw item. Returns null if the id is missing.
function normalizeItem(raw: any): VintedItem | null {
  if (raw?.id == null) return null;
  const sellerId = raw.user?.id ?? raw.user_id ?? null;
  return {
    id: String(raw.id),
    title: raw.title ?? '(untitled)',
    price: parsePrice(raw),
    brand: raw.brand_title ?? raw.brand?.title ?? null,
    size: raw.size_title ?? raw.size ?? null,
    photos: parsePhotos(raw),
    url: raw.url ?? null,
    sellerId: sellerId != null ? String(sellerId) : null,
  };
}

// Takes the raw WebSocket text (catalog API JSON) and extracts the list of
// normalized items. Defensive: any unexpected shape → [].
export function parseFeedMessage(text: string): VintedItem[] {
  let data: any;
  try {
    data = JSON.parse(text);
  } catch {
    return [];
  }

  const rawItems: any[] =
    Array.isArray(data) ? data :
    Array.isArray(data?.items) ? data.items :
    Array.isArray(data?.catalogItems) ? data.catalogItems :
    [];

  const out: VintedItem[] = [];
  for (const raw of rawItems) {
    const item = normalizeItem(raw);
    if (item) out.push(item);
  }
  return out;
}

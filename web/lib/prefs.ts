// User preferences local to the browser (localStorage).

const INSTANT_BUY_KEY = 'vlf_instant_buy';

/** True if fastbuy should skip the confirmation (immediate purchase on click). */
export function getInstantBuy(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(INSTANT_BUY_KEY) === '1';
}

export function setInstantBuy(on: boolean): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(INSTANT_BUY_KEY, on ? '1' : '0');
}

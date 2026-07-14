'use client';

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from 'react';
import { parseFeedMessage, type VintedItem } from '@/lib/types';
import { getFeedTicket } from '@/lib/feedTicket';

export type FeedStatus = 'connecting' | 'open' | 'closed' | 'paused';

const WS_URL =
  process.env.NEXT_PUBLIC_FEED_WS_URL ?? 'ws://localhost:5000/ws';

// After this idle time (or when the tab is hidden) the feed PAUSES:
// it closes the WS → no scraping → no proxy usage. Resumes on activity.
const IDLE_MS = 2 * 60 * 1000; // 2 minutes

// useLayoutEffect would warn on the server: we only use it in the browser.
const useIsoLayoutEffect =
  typeof window !== 'undefined' ? useLayoutEffect : useEffect;

/**
 * Connects to the feed WebSocket, normalizes messages and keeps a list of
 * items deduplicated by id (new ones go on top). Reconnects on its own.
 *
 * `search` is the filter query (catalog/items querystring): it's passed to the
 * WS and, when it changes, the feed is reset and the connection reopened.
 *
 * `scrollRef` is the scrolling container (the cards area): the anti-jump acts
 * on that instead of on the window.
 */
export function useFeed(
  search: string = '',
  scrollRef?: RefObject<HTMLElement | null>,
  columns: number = 2,
) {
  const [items, setItems] = useState<VintedItem[]>([]);
  const [status, setStatus] = useState<FeedStatus>('connecting');
  // Paused (idle or tab in background): the WS stays closed.
  const [paused, setPaused] = useState(false);
  // Just-arrived ids: to animate the entrance of ONLY the new cards.
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const newClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ids already seen, so we don't re-insert the same items on every poll.
  const seen = useRef<Set<string>>(new Set());

  // Page height before the last insertion, for scroll anti-jump.
  const prevHeight = useRef(0);
  // "Existing cards slide down slowly" animation when new items arrive.
  const revealAnim = useRef<number | null>(null);
  const atTop = useRef(true); // is the user looking at the top of the feed?
  // Reference card (the first of the previous render) to measure how far the
  // existing content actually MOVED DOWN, without being fooled by spacers.
  const prevRefId = useRef<string | null>(null);
  const prevRefTop = useRef(0);

  // Presence: pause after IDLE_MS with no activity or when the tab is hidden.
  useEffect(() => {
    let last = Date.now();
    // User activity → mark the time and, if we were paused, resume.
    // NB: no 'scroll' event here — the anti-jump scrolls on its own and would
    // skew idleness; we use 'wheel'/'touchstart' for user-initiated scrolling.
    const bump = () => {
      last = Date.now();
      setPaused((p) => (p ? false : p));
    };
    const onVisibility = () => {
      if (document.hidden) {
        setPaused(true);
      } else {
        last = Date.now();
        setPaused(false);
      }
    };
    const evts = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart'];
    evts.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    document.addEventListener('visibilitychange', onVisibility);
    const check = setInterval(() => {
      if (!document.hidden && Date.now() - last >= IDLE_MS) setPaused(true);
    }, 20000);
    return () => {
      evts.forEach((e) => window.removeEventListener(e, bump));
      document.removeEventListener('visibilitychange', onVisibility);
      clearInterval(check);
    };
  }, []);

  // Filter change → reset the feed (separate from the connection, so pausing
  // doesn't clear the accumulated items).
  useEffect(() => {
    seen.current = new Set();
    setItems([]);
  }, [search]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    // Without filters we don't connect to the feed (no fetching of every product).
    if (!search) {
      setStatus('closed');
      return;
    }
    // Paused: don't connect (and the cleanup already closed the previous WS).
    if (paused) {
      setStatus('paused');
      return;
    }

    const connect = async () => {
      setStatus('connecting');
      // Access ticket (subscription): without it, the feed refuses the connection.
      const ticket = await getFeedTicket();
      if (closed) return;
      const url = `${WS_URL}?ticket=${encodeURIComponent(ticket ?? '')}&${search}`;
      ws = new WebSocket(url);

      ws.onopen = () => setStatus('open');

      ws.onmessage = (ev) => {
        const incoming = parseFeedMessage(ev.data);
        const fresh = incoming.filter((it) => !seen.current.has(it.id));
        if (fresh.length === 0) return;

        for (const it of fresh) seen.current.add(it.id);
        // TEST: no limit, all items accumulate (no trimming).
        setItems((prev) => [...fresh, ...prev]);
        // Mark the new ids for the entrance animation, then clear them.
        setNewIds(new Set(fresh.map((it) => it.id)));
        if (newClearTimer.current) clearTimeout(newClearTimer.current);
        newClearTimer.current = setTimeout(() => setNewIds(new Set()), 700);
      };

      ws.onclose = () => {
        setStatus('closed');
        if (!closed) reconnectTimer = setTimeout(connect, 2000);
      };

      ws.onerror = () => ws?.close();
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [search, paused]);

  // Tracks whether the user is at the top and stops the animation if they scroll.
  useEffect(() => {
    const el = scrollRef?.current;
    if (!el) return;
    const onScroll = () => {
      // During the reveal the scroll is ours: don't update 'atTop'.
      if (revealAnim.current == null) atTop.current = el.scrollTop <= 4;
    };
    const onUserScroll = () => {
      if (revealAnim.current != null) {
        cancelAnimationFrame(revealAnim.current);
        revealAnim.current = null;
        atTop.current = el.scrollTop <= 4;
      }
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    el.addEventListener('wheel', onUserScroll, { passive: true });
    el.addEventListener('touchstart', onUserScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      el.removeEventListener('wheel', onUserScroll);
      el.removeEventListener('touchstart', onUserScroll);
      if (revealAnim.current != null) cancelAnimationFrame(revealAnim.current);
    };
  }, [scrollRef]);

  // Inserting the new items:
  //  - ALWAYS keeps the current view still (anti-jump: the new stuff is above);
  //  - if the user is AT THE TOP, it then scrolls smoothly to 0 → the existing
  //    cards "slide down" slowly to make room for the new ones. If they're
  //    scrolled down, no animation (we don't disturb them).
  useIsoLayoutEffect(() => {
    const el = scrollRef?.current;
    if (!el) {
      const newHeight = document.documentElement.scrollHeight;
      const d = newHeight - prevHeight.current;
      prevHeight.current = newHeight;
      if (d > 0 && window.scrollY > 0) window.scrollBy(0, d);
      return;
    }
    // How far a reference existing card (the first of the previous render)
    // actually MOVED DOWN. offsetTop is independent of scroll → it distinguishes
    // "a row was added above" (must move down) from "the same row got filled or
    // a row that widens" (must not move down → no jerk). See spacer bug.
    const topOf = (id: string | null) => {
      if (!id) return null;
      const node = el.querySelector(
        `[data-feed-id="${CSS.escape(id)}"]`,
      ) as HTMLElement | null;
      return node ? node.offsetTop : null;
    };
    const refNewTop = topOf(prevRefId.current);
    const displacement = refNewTop != null ? refNewTop - prevRefTop.current : 0;
    prevHeight.current = el.scrollHeight;

    // Anti-jump: keep the reference card still (it's VISIBLE → real offsetTop).
    if (displacement > 0) el.scrollTop += displacement;

    // New anchor = first CURRENTLY VISIBLE card. Crucial: off-screen cards have
    // content-visibility:auto → ESTIMATED offsetTop (430px), which skews the
    // compensation when the user is mid-list. A visible card has its real
    // height → precise anti-jump.
    const top = el.scrollTop;
    const nodes = el.querySelectorAll('[data-feed-id]');
    let anchor: HTMLElement | null = nodes.length
      ? (nodes[nodes.length - 1] as HTMLElement)
      : null;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i] as HTMLElement;
      if (n.offsetTop + n.offsetHeight > top + 4) {
        anchor = n;
        break;
      }
    }
    prevRefId.current = anchor?.getAttribute('data-feed-id') ?? null;
    prevRefTop.current = anchor ? anchor.offsetTop : 0;

    if (displacement <= 0) return;
    if (!atTop.current) return; // scrolled down → stop (no animation)

    // Reveal by scrolling from 'displacement' down to 0 with easing → slow descent.
    if (revealAnim.current != null) cancelAnimationFrame(revealAnim.current);
    const from = el.scrollTop;
    const start = performance.now();
    const REVEAL_MS = 600;
    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / REVEAL_MS);
      el.scrollTop = Math.round(from * (1 - easeOut(t)));
      revealAnim.current = t < 1 ? requestAnimationFrame(step) : null;
    };
    revealAnim.current = requestAnimationFrame(step);
  }, [items]);

  return { items, status, newIds };
}

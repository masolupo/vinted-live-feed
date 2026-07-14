'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useFeed } from '@/hooks/useFeed';
import { createClient } from '@/utils/supabase/client';
import { ItemCard } from '@/components/ItemCard';
import { ConnectionStatus } from '@/components/ConnectionStatus';
import { FilterPanel } from '@/components/filters/FilterPanel';
import { Button } from '@/components/ui/Button';
import {
  buildFeedQuery,
  buildSummary,
  countActiveFilters,
  emptySelection,
  type FilterSelection,
} from '@/lib/filters';
import styles from './page.module.css';

// Number of columns in the feed grid.
const COLUMNS = 4;

export default function FeedPage() {
  // Applied filter selection (the one active on the feed).
  const [applied, setApplied] = useState<FilterSelection>(emptySelection);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Vinted account connection status, for the dot in the header.
  const [vintedStatus, setVintedStatus] =
    useState<'loading' | 'none' | 'connected' | 'expired'>('loading');
  useEffect(() => {
    fetch('/api/vinted/status')
      .then((r) => (r.ok ? r.json() : { status: 'none' }))
      .then((d) => setVintedStatus(d.status ?? 'none'))
      .catch(() => setVintedStatus('none'));
  }, []);

  // Heartbeat: while the Vinted account is connected and VLS is open, signal
  // presence to the server (every 4 min) so the worker keeps the access token fresh.
  useEffect(() => {
    if (vintedStatus !== 'connected') return;
    const ping = () =>
      fetch('/api/vinted/heartbeat', { method: 'POST' }).catch(() => {});
    ping();
    const id = setInterval(ping, 4 * 60 * 1000);
    return () => clearInterval(id);
  }, [vintedStatus]);

  const vintedDotColor =
    vintedStatus === 'connected'
      ? '#3ddc84'
      : vintedStatus === 'expired'
        ? '#ffb020'
        : 'var(--text-muted)';

  const logout = async () => {
    await createClient().auth.signOut();
    router.push('/login');
    router.refresh();
  };

  const active = countActiveFilters(applied);
  // With no filters we fetch NOTHING: empty query = no connection.
  const query = active > 0 ? buildFeedQuery(applied) : '';
  const summary = buildSummary(applied);

  const { items, status, newIds } = useFeed(query, scrollRef, COLUMNS);

  // Empty leading cells to reach a multiple of COLUMNS: last row always full
  // and each item stays in its column when more arrive.
  const spacerCount = (COLUMNS - (items.length % COLUMNS)) % COLUMNS;

  return (
    <main className={styles.main}>
      <FilterPanel
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        onApply={setApplied}
      />

      <section className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <Button onClick={() => setFiltersOpen(true)}>
              ☰ Filters{active ? ` (${active})` : ''}
            </Button>
            <div>
              <h1 className={styles.title}>Live Feed</h1>
              <p className={styles.subtitle}>{items.length} items</p>
            </div>
          </div>
          <div className={styles.headerRight}>
            {active > 0 && <ConnectionStatus status={status} />}
            <Button
              variant="ghost"
              onClick={() => router.push('/account')}
              title={
                vintedStatus === 'connected'
                  ? 'Vinted account connected'
                  : vintedStatus === 'expired'
                    ? 'Vinted session expired'
                    : 'Vinted account not connected'
              }
            >
              <span
                className={styles.accountDot}
                style={{ background: vintedDotColor }}
              />
              Vinted account
            </Button>
            <Button variant="ghost" onClick={logout}>
              Log out
            </Button>
          </div>
        </header>

        {active > 0 && summary && (
          <div className={styles.summary} title="Active filter">
            {summary}
          </div>
        )}

        <div ref={scrollRef} className={`${styles.scrollArea} prettyScroll`}>
          {active === 0 ? (
            <div className={styles.empty}>
              <p>Set a filter to see the feed.</p>
              <Button onClick={() => setFiltersOpen(true)}>Choose a filter</Button>
            </div>
          ) : items.length === 0 ? (
            <div className={styles.empty}>Waiting for new items from the feed…</div>
          ) : (
            <div
              className={styles.grid}
              style={{ gridTemplateColumns: `repeat(${COLUMNS}, 1fr)` }}
            >
              {/* Empty leading cells (on the left) to keep the last row
                  full and the items stable in their column. */}
              {Array.from({ length: spacerCount }).map((_, i) => (
                <div key={`spacer-${i}`} aria-hidden className={styles.spacer} />
              ))}
              {items.map((item) => (
                <ItemCard
                  key={item.id}
                  item={item}
                  canBuy={vintedStatus === 'connected'}
                  isNew={newIds.has(item.id)}
                />
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

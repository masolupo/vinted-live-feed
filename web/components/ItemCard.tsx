'use client';

import { useState, type ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PhotoGallery } from '@/components/PhotoGallery';
import type { VintedItem } from '@/lib/types';
import { getInstantBuy } from '@/lib/prefs';
import styles from './ItemCard.module.css';

// How many thumbnails to show at most; beyond that, the last becomes "+N".
const MAX_THUMBS = 4;

// Wraps in a link to the listing (if there's a url), otherwise renders the children bare.
function Linkable({ url, children }: { url: string | null; children: ReactNode }) {
  if (!url) return <>{children}</>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

type BuyState = 'idle' | 'confirm' | 'buying' | 'reserved' | 'done' | 'action' | 'error';

type Pickup = {
  carrier?: string;
  point?: string;
  name?: string | null;
  address?: string | null;
};

export function ItemCard({
  item,
  canBuy = false,
  isNew = false,
}: {
  item: VintedItem;
  canBuy?: boolean;
  isNew?: boolean;
}) {
  const [idx, setIdx] = useState(0);
  const [galleryOpen, setGalleryOpen] = useState(false);

  const [buyState, setBuyState] = useState<BuyState>('idle');
  const [buyMsg, setBuyMsg] = useState<string | null>(null);
  const [buyPickup, setBuyPickup] = useState<Pickup | null>(null);

  // Maps a progress event (NDJSON from the feed) to the button state.
  const handleEvent = (ev: { phase?: string; payment_status?: string; pickup?: Pickup; error?: string }) => {
    switch (ev.phase) {
      case 'preparing':
        setBuyState('buying'); // "Preparing…" (checkout in progress)
        break;
      case 'paying':
        // payment starts → Vinted reserves the item (15 min): it's "Got it!"
        setBuyState('reserved');
        break;
      case 'done': {
        const ps = ev.payment_status;
        if (ps === 'success' || ps === 'completed') {
          setBuyPickup(ev.pickup ?? null);
          setBuyState('done');
        } else {
          setBuyState('error');
          setBuyMsg(`Payment outcome: ${ps ?? 'unknown'}`);
        }
        break;
      }
      case 'requires_action': // 3DS: reserved, but the payment must be confirmed manually
        setBuyPickup(ev.pickup ?? null);
        setBuyState('action');
        break;
      case 'error':
        setBuyState('error');
        setBuyMsg(ev.error ?? 'Purchase failed.');
        break;
    }
  };

  const doBuy = async () => {
    setBuyState('buying');
    setBuyMsg(null);
    setBuyPickup(null);
    try {
      const res = await fetch('/api/vinted/buy', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ itemId: item.id, sellerId: item.sellerId }),
      });
      if (!res.ok || !res.body) {
        const d = await res.json().catch(() => ({}));
        setBuyState('error');
        setBuyMsg(d.error ?? 'Purchase failed.');
        return;
      }
      // NDJSON stream: one JSON line per progress event.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let sawTerminal = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          let ev;
          try {
            ev = JSON.parse(line);
          } catch {
            continue;
          }
          if (ev.phase === 'done' || ev.phase === 'error' || ev.phase === 'requires_action') {
            sawTerminal = true;
          }
          handleEvent(ev);
        }
      }
      if (!sawTerminal) {
        setBuyState('error');
        setBuyMsg('Purchase interrupted — check on Vinted.');
      }
    } catch {
      setBuyState('error');
      setBuyMsg('Network error.');
    }
  };

  const showBuy = canBuy && !!item.sellerId;

  const photos = item.photos;
  const main = photos[idx] ?? photos[0] ?? null;
  // Thumbnails = all photos EXCEPT the one currently shown large (no duplicate).
  const others = photos
    .map((p, i) => ({ p, i }))
    .filter((x) => x.i !== idx);
  const hasThumbs = others.length >= 1;
  const shown = others.slice(0, MAX_THUMBS);
  const extra = others.length - MAX_THUMBS; // > 0 if there are still more

  return (
    <Card
      className={`${styles.card}${isNew ? ` ${styles.cardIn}` : ''}`}
      data-feed-id={item.id}
    >
      {main ? (
        <button
          type="button"
          className={styles.photoBtn}
          onClick={() => setGalleryOpen(true)}
          aria-label="View all photos"
        >
          <div className={styles.photo}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={main.url} alt={item.title} loading="lazy" />
          </div>
        </button>
      ) : (
        <div className={styles.photo}>
          <div className={styles.noPhoto}>no photo</div>
        </div>
      )}

      {/* Thumbnail row: always MAX_THUMBS slots (missing ones are invisible),
          so the row has the same height on every card. The thumbnails adapt
          in width. */}
      <div className={styles.thumbs}>
        {Array.from({ length: MAX_THUMBS }).map((_, slot) => {
          const entry = hasThumbs ? shown[slot] : undefined;
          if (!entry) return <div key={slot} className={styles.thumbSlot} aria-hidden />;
          // The last thumbnail, when there are more photos beyond those shown,
          // becomes the "+N" and opens the gallery with ALL the photos.
          const isMore = slot === MAX_THUMBS - 1 && extra > 0;
          return (
            <button
              key={slot}
              type="button"
              className={styles.thumb}
              onClick={() => (isMore ? setGalleryOpen(true) : setIdx(entry.i))}
              aria-label={isMore ? 'View all photos' : `Photo ${entry.i + 1}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={entry.p.thumb} alt="" loading="lazy" />
              {isMore && <span className={styles.more}>+{extra}</span>}
            </button>
          );
        })}
      </div>

      <Linkable url={item.url}>
        <div className={styles.body}>
          <div className={styles.title}>{item.title}</div>
          {/* Always present (even if empty) to keep the height fixed. */}
          <div className={styles.price}>{item.price ?? ''}</div>
          <div className={styles.meta}>
            {item.brand && <Badge>{item.brand}</Badge>}
            {item.size && <Badge>{item.size}</Badge>}
          </div>
        </div>
      </Linkable>

      {showBuy ? (
        <div className={styles.buy}>
          {buyState === 'idle' && (
            <button
              type="button"
              className={styles.buyBtn}
              onClick={() => (getInstantBuy() ? doBuy() : setBuyState('confirm'))}
            >
              ⚡ Fastbuy
            </button>
          )}

          {buyState === 'confirm' && (
            <div className={styles.buyConfirm}>
              <span className={styles.buyAsk}>
                Buy{item.price ? ` for ${item.price}` : ''}?
              </span>
              <div className={styles.buyActions}>
                <button type="button" className={styles.buyYes} onClick={doBuy}>
                  Confirm
                </button>
                <button
                  type="button"
                  className={styles.buyNo}
                  onClick={() => setBuyState('idle')}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {buyState === 'buying' && (
            <button type="button" className={styles.buyBtn} disabled>
              ⏳ Preparing…
            </button>
          )}

          {buyState === 'reserved' && <p className={styles.buyHit}>🎯 Got it!</p>}

          {buyState === 'done' && (
            <div>
              <p className={styles.buyHit}>🎉 Got it!</p>
              {buyPickup && (
                <span className={styles.buyPickup}>
                  Pickup: {buyPickup.name ?? buyPickup.carrier}
                  {buyPickup.address ? ` · ${buyPickup.address}` : ''}
                </span>
              )}
            </div>
          )}

          {buyState === 'action' && (
            <div>
              <p className={`${styles.buyHit} ${styles.buyAction}`}>🎯 Got it!</p>
              <span className={styles.buyPickup}>
                Confirm the payment on Vinted (3DS) within 15 min
              </span>
            </div>
          )}

          {buyState === 'error' && (
            <div className={styles.buyConfirm}>
              <span className={styles.buyErr}>{buyMsg}</span>
              <button
                type="button"
                className={styles.buyNo}
                onClick={() => setBuyState('idle')}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      ) : canBuy ? (
        // Connected but no seller: reserved empty area → fixed height.
        <div className={styles.buy} aria-hidden />
      ) : null}

      {galleryOpen && (
        <PhotoGallery
          photos={photos}
          title={item.title}
          url={item.url}
          onClose={() => setGalleryOpen(false)}
        />
      )}
    </Card>
  );
}

'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { VintedPhoto } from '@/lib/types';
import styles from './PhotoGallery.module.css';

interface Props {
  photos: VintedPhoto[];
  title: string;
  url: string | null;
  onClose: () => void;
}

/**
 * Full-screen gallery: shows all the photos enlarged, in a scrolling grid.
 * Closes with Esc, by clicking the backdrop or the ✕. Rendered in a portal on
 * <body> so it isn't affected by the card's transform.
 */
export function PhotoGallery({ photos, title, url, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    // Block scrolling of the page underneath while the gallery is open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  // Near-square grid that adapts to the number of photos: they all fit in the
  // fixed box, shrinking/growing (no scroll).
  const n = photos.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
  const rows = Math.max(1, Math.ceil(n / cols));
  const gridStyle = {
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    gridTemplateRows: `repeat(${rows}, 1fr)`,
  };

  return createPortal(
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.dialog}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`Photos of ${title}`}
      >
        <header className={styles.header}>
          <span className={styles.title}>
            {title} <span className={styles.count}>· {photos.length} photos</span>
          </span>
          <div className={styles.actions}>
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.link}
              >
                Open on Vinted
              </a>
            )}
            <button
              type="button"
              className={styles.close}
              onClick={onClose}
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </header>

        <div className={styles.grid} style={gridStyle}>
          {photos.map((p, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={p.url}
              alt={`${title} — photo ${i + 1}`}
              className={styles.photo}
              loading="lazy"
            />
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}

import type { FeedStatus } from '@/hooks/useFeed';
import styles from './ConnectionStatus.module.css';

const LABELS: Record<FeedStatus, string> = {
  connecting: 'Connecting…',
  open: 'Listening',
  closed: 'Disconnected',
  paused: 'Paused — move the mouse to resume',
};

export function ConnectionStatus({ status }: { status: FeedStatus }) {
  return (
    <span className={styles.wrap}>
      <span className={`${styles.dot} ${styles[status]}`} />
      {LABELS[status]}
    </span>
  );
}

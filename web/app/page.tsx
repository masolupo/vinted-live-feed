import type { Metadata } from 'next';
import Link from 'next/link';
import styles from './page.module.css';

const GITHUB_URL = 'https://github.com/masolupo/vinted-live-feed';

// Public showcase (route "/"): the first thing logged-out visitors see.
// Logged-in visitors are redirected by the middleware to /feed.
export const metadata: Metadata = {
  title: 'Blim — Vinted live feed & fastbuy (open source)',
  description:
    'Real-time Vinted feed + one-click buying. Open-source project: advanced filters, automatic pickup, account management. Self-hostable.',
  openGraph: {
    title: 'Blim — Vinted live feed & fastbuy (open source)',
    description:
      'Real-time Vinted feed and one-click buying. Open-source project, self-hostable.',
    type: 'website',
  },
};

// How it works, in 3 steps.
const STEPS = [
  {
    n: '1',
    title: 'Connect your account',
    text: 'Sign in with your Vinted account securely. It only takes a few seconds.',
  },
  {
    n: '2',
    title: 'Set your filters',
    text: 'Category, brand, size, price, color: choose exactly what to look for.',
  },
  {
    n: '3',
    title: 'Buy on the fly',
    text: 'As soon as a listing that fits you appears, you grab it in one click. Before everyone else.',
  },
];

// The key features.
const FEATURES = [
  {
    icon: '🔴',
    title: 'Real-time feed',
    text: 'New listings appear the moment they go live on Vinted, without reloading the page.',
  },
  {
    icon: '⚡',
    title: 'One-click fastbuy',
    text: 'Automatic checkout: from click to payment in seconds, when every second counts.',
  },
  {
    icon: '🎯',
    title: 'Advanced filters',
    text: 'Narrow down by category, brand, size, price and color. See only what interests you.',
  },
  {
    icon: '📦',
    title: 'Automatic pickup',
    text: 'Shipping and pickup point handled for you: InPost, BRT, Poste or home delivery.',
  },
];

// Frequently asked questions — honest answers, no inflated promises.
const FAQ = [
  {
    q: 'Do you need my Vinted password?',
    a: 'Yes: to buy on your behalf you connect your Vinted account. The credentials are used solely to operate on your account, stored encrypted, and shown to no one.',
  },
  {
    q: 'How fast is the purchase?',
    a: 'With good deals, whoever gets there first wins. With Blim all it takes is one click: address, payment and pickup point are already set, so you skip all the checkout steps.',
  },
  {
    q: 'How much does it cost?',
    a: 'Nothing: Blim is an open-source project. The code is public and you can self-host it for free — you bring your own proxies and your own anti-captcha key.',
  },
  {
    q: 'Which countries does it work in?',
    a: 'It is designed mainly for Italy (Vinted Italy), but the domain is configurable: it runs on any Vinted (.it/.fr/.de…).',
  },
  {
    q: 'Is it safe for my account?',
    a: 'Blim operates on your account as naturally as possible. No tool can guarantee zero risk, but we do everything we can to keep it to a minimum. This is an educational project: use it responsibly.',
  },
  {
    q: 'Can I see or modify the code?',
    a: 'Yes. It is open-source on GitHub: you can study it, fork it and contribute.',
  },
];

export default function LandingPage() {
  return (
    <div className={`${styles.page} prettyScroll`}>
      {/* Top bar */}
      <nav className={styles.nav}>
        <span className={styles.logo}>Blim</span>
        <div className={styles.navActions}>
          <a href={GITHUB_URL} className={styles.navLink} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
          <Link href="/login" className={styles.btnPrimary}>
            Sign in
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <header className={styles.hero}>
        <span className={styles.badge}>🔓 Open-source project</span>
        <h1 className={styles.h1}>
          Buy on Vinted
          <br />
          <span className={styles.accent}>before everyone else</span>.
        </h1>
        <p className={styles.lead}>
          Blim shows you new listings in real time and lets you buy in one
          click. No obsessive refreshing: the best deals come to you.
        </p>
        <div className={styles.heroCtas}>
          <Link href="/login" className={styles.btnPrimaryLg}>
            Sign in
          </Link>
          <a href={GITHUB_URL} className={styles.btnGhostLg} target="_blank" rel="noopener noreferrer">
            Code on GitHub
          </a>
        </div>
        <div className={styles.trust}>
          <span>⚡ One-click buying</span>
          <span>🔴 Real-time feed</span>
          <span>🇮🇹 Built for Italy</span>
        </div>
      </header>

      {/* How it works */}
      <section className={styles.section}>
        <h2 className={styles.h2}>How it works</h2>
        <div className={styles.steps}>
          {STEPS.map((s) => (
            <div key={s.n} className={styles.step}>
              <span className={styles.stepNum}>{s.n}</span>
              <h3 className={styles.cardTitle}>{s.title}</h3>
              <p className={styles.cardText}>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className={styles.section}>
        <h2 className={styles.h2}>Everything you need</h2>
        <div className={styles.features}>
          {FEATURES.map((f) => (
            <div key={f.title} className={styles.feature}>
              <span className={styles.featureIcon}>{f.icon}</span>
              <h3 className={styles.cardTitle}>{f.title}</h3>
              <p className={styles.cardText}>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Open source */}
      <section className={styles.section}>
        <h2 className={styles.h2}>Open source, self-hostable</h2>
        <div className={styles.pricing}>
          <span className={styles.priceBadge}>Open code</span>
          <p className={styles.priceText}>
            Blim is <strong>free and open-source</strong>. Clone the repo, bring your
            own proxies and your own anti-captcha key, and host it wherever you want.
          </p>
          <ul className={styles.priceList}>
            <li>✓ Real-time feed of new listings</li>
            <li>✓ One-click fastbuy</li>
            <li>✓ Filters by category, brand, price, size and color</li>
            <li>✓ Pickup point management</li>
          </ul>
          <a href={GITHUB_URL} className={styles.btnPrimaryLg} target="_blank" rel="noopener noreferrer">
            See the code on GitHub
          </a>
        </div>
      </section>

      {/* FAQ */}
      <section className={styles.section}>
        <h2 className={styles.h2}>Frequently asked questions</h2>
        <div className={styles.faq}>
          {FAQ.map((item) => (
            <details key={item.q} className={styles.faqItem}>
              <summary className={styles.faqQ}>{item.q}</summary>
              <p className={styles.faqA}>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className={styles.finalCta}>
        <h2 className={styles.h2}>Ready to beat everyone to it?</h2>
        <Link href="/login" className={styles.btnPrimaryLg}>
          Sign in
        </Link>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <span className={styles.logo}>Blim</span>
        <p className={styles.footNote}>
          Blim is an independent, educational tool, and is not affiliated with,
          associated with or sponsored by Vinted.
        </p>
        <div className={styles.footLinks}>
          <a href={GITHUB_URL} className={styles.navLink} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </div>
        <p className={styles.copy}>© 2026 Blim</p>
      </footer>
    </div>
  );
}

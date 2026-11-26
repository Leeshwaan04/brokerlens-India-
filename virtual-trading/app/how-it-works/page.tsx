import type { Metadata } from "next";
import Link from "next/link";
import { AppHeader } from "@/components/AppHeader";
import { FillRules } from "@/components/FillRules";
import { SiteFooter } from "@/components/SiteFooter";
import { buttonClass, Card, cx } from "@/components/ui";
import { MIS_MARGIN_PCT } from "@/lib/fills";
import { priceLagDays } from "@/lib/market-clock";
import { getSessionUserId } from "@/lib/session";
import { APP_URL, SITE_NAME } from "@/lib/site";

export const metadata: Metadata = {
  title: "How paper trading works here: orders, fills, intraday and charges",
  description:
    "The rules of BrokerLens's practice market: market, limit, stop-loss and GTT orders, after-market orders, intraday margin and square-off, and how every broker's real charges are applied.",
  alternates: { canonical: "/how-it-works" },
};

const SECTIONS = [
  { id: "market", title: "The practice market" },
  { id: "orders", title: "Order types and validity" },
  { id: "fills", title: "How orders fill" },
  { id: "intraday", title: "Intraday (MIS)" },
  { id: "charges", title: "Charges and taxes" },
  { id: "limits", title: "What this is not" },
];

export default async function HowItWorksPage() {
  const signedIn = (await getSessionUserId()) !== null;
  const lag = priceLagDays();
  const margin = Math.round(MIS_MARGIN_PCT * 100);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "How paper trading works on BrokerLens Virtual Trading",
    url: `${APP_URL}/how-it-works`,
    inLanguage: "en-IN",
    isPartOf: { "@type": "WebSite", name: SITE_NAME, url: APP_URL },
    publisher: { "@type": "Organization", name: "BrokerLens", url: "https://www.brokerlens.in/" },
  };

  return (
    <>
      <AppHeader signedIn={signedIn} />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10 sm:px-6">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
        <p className="text-sm font-medium text-accent-ink">How it works</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">How paper trading works here</h1>
        <p className="mt-3 text-muted">
          The practice market follows the rules a real broker&apos;s order window does, with official NSE prices and every
          charge applied. These are the rules, in full.
        </p>
        <nav aria-label="On this page" className="mt-6 flex flex-wrap gap-2 text-sm">
          {SECTIONS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="rounded-full border border-line px-3 py-1 text-muted hover:border-accent hover:text-ink">
              {s.title}
            </a>
          ))}
        </nav>

        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-ink [&_li]:text-muted [&_p]:text-muted">
          <Card>
            <h2 id="market" className="scroll-mt-24">The practice market</h2>
            <p className="mt-2">
              You trade the Nifty 100 with ₹10,00,000 of virtual cash. The practice market runs {lag} days behind the real one:
              {lag > 0
                ? ` if today is 25 November, the practice market is on 26 October, with that day's session, holidays and official NSE prices. Every price you see is at least ${lag} days old.`
                : " it follows the real calendar, with official closes published each evening."}{" "}
              Sessions open at 9:15 and close at 15:30, and a day&apos;s prices appear once its session has closed.
            </p>
          </Card>

          <Card>
            <h2 id="orders" className="scroll-mt-24">Order types and validity</h2>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5">
              <li>
                <span className="text-ink">Market:</span> placed before the session opens (an after-market order), it fills at
                the open; placed during the session, at the close.
              </li>
              <li>
                <span className="text-ink">Limit:</span> buys at your price or lower, sells at your price or higher.
              </li>
              <li>
                <span className="text-ink">Stop-loss (SL-M):</span> becomes a market order when its trigger price trades. A sell
                stop sits below the last close, a buy stop above it.
              </li>
              <li>
                <span className="text-ink">Day or GTT:</span> a day order ends with its session; a GTT (good till triggered)
                order is checked every session for up to a year.
              </li>
              <li>Limit and trigger prices must be within 20% of the last close, to two decimal places.</li>
            </ul>
          </Card>

          <Card>
            <h2 id="fills" className="scroll-mt-24">How orders fill</h2>
            <FillRules />
          </Card>

          <Card>
            <h2 id="intraday" className="scroll-mt-24">Intraday (MIS)</h2>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5">
              <li>
                An intraday position opens and closes in the same session, on {margin}% margin (up to {Math.round(100 / margin)}x).
                You can buy first or short-sell first.
              </li>
              <li>Add an optional stop-loss and target. Whatever is still open is squared off at the 15:30 close.</li>
              <li>Profit or loss after charges goes straight to your cash. Nothing reaches your holdings.</li>
            </ul>
          </Card>

          <Card>
            <h2 id="charges" className="scroll-mt-24">Charges and taxes</h2>
            <p className="mt-2">
              Every order is charged with your practice broker&apos;s published brokerage plus the statutory charges, leg by leg,
              as a contract note would show them:
            </p>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5">
              <li>Delivery: STT 0.1% on both the buy and the sell, stamp duty 0.015% on the buy, DP charge on the sell.</li>
              <li>Intraday: STT 0.025% on the sell, stamp duty 0.003% on the buy, no DP charge.</li>
              <li>Both: NSE transaction charges 0.00297%, SEBI fees ₹10 per crore, GST 18% on brokerage and those fees.</li>
            </ul>
            <p className="mt-2">
              The Broker costs page then replays your own delivery trades at every broker whose full fee schedule BrokerLens
              holds, ranked by cost alone.
            </p>
          </Card>

          <Card>
            <h2 id="limits" className="scroll-mt-24">What this is not</h2>
            <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5">
              <li>No real money moves and no order reaches an exchange. Virtual profits cannot be withdrawn.</li>
              <li>It is a practice tool for learning how orders, charges and risk work, not investment advice or a tip service.</li>
              <li>
                With only each day&apos;s open, high, low and close, fills are an approximation of a live session, and the rules
                above lean towards the worse price on purpose.
              </li>
            </ul>
          </Card>
        </div>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link href={signedIn ? "/trade" : "/sign-up"} className={cx(buttonClass("primary"), "px-6 py-3")}>
            {signedIn ? "Go to the trade screen" : "Start practising free"}
          </Link>
          <Link href="/" className={cx(buttonClass("secondary"), "px-6 py-3")}>
            Compare broker charges
          </Link>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}

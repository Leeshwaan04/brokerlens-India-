import Link from "next/link";
import { redirect } from "next/navigation";
import { after } from "next/server";
import { readCampaign, track } from "@/lib/events";
import { APP_URL, SITE_NAME } from "@/lib/site";
import { getSessionUserId } from "@/lib/session";
import { getAllBrokers, toReplayBroker } from "@/lib/brokers";
import { rankBrokersForFills } from "@/lib/cost-replay";
import { latestTradeDates } from "@/lib/prices";
import { inr, inrWhole, shortDate } from "@/lib/format";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { RankingTable } from "@/components/RankingTable";
import { buttonClass, cx } from "@/components/ui";

const AMOUNTS = [10_000, 50_000, 1_00_000, 5_00_000, 10_00_000];

const STEPS = [
  {
    title: "Pick a broker to practise with",
    body: "Your virtual orders are costed with its real, published fee schedule. Switch any time.",
  },
  {
    title: "Trade Nifty 500 stocks with ₹10 lakh of virtual cash",
    body: "Market, limit, stop-loss and GTT orders, delivery or intraday, with every charge shown before you place it. Orders fill against official NSE prices, never instantly.",
  },
  {
    title: "Replay your trades at every broker",
    body: "Find out which broker would actually have charged you least for the way you trade, before you open a real account.",
  },
];

const FAQ = [
  {
    q: "Is BrokerLens Virtual Trading free?",
    a: "Yes. Practising is free: ₹10 lakh of virtual cash, every order type and both delivery and intraday. An optional Plus pass adds a downloadable statement of your practice trades.",
  },
  {
    q: "Is any real money involved, or a real broker account?",
    a: "No. Orders never reach an exchange, no real money moves and no broker account is opened. Virtual profits cannot be withdrawn.",
  },
  {
    q: "Where do the prices come from, and why are they not live?",
    a: "Prices are NSE's official open, high, low and close for each session. The practice market runs 30 days behind the real one, so every price is at least 30 days old, and orders fill against those official prices by published rules.",
  },
  {
    q: "What can I practise?",
    a: "Nifty 500 stocks, delivery (CNC) and intraday (MIS) including short selling, with market, limit and stop-loss orders, valid for the day or GTT for up to a year.",
  },
  {
    q: "How are charges calculated?",
    a: "Each order is charged with your practice broker's published brokerage plus STT, NSE transaction charges, SEBI fees, stamp duty, GST and DP charges, leg by leg. You can switch broker at any time and replay your trades at every broker.",
  },
  {
    q: "Does BrokerLens earn from brokers?",
    a: "Some account-opening links are referral links, so BrokerLens may earn a fee if you open an account through them. That never changes the fees shown or the order of any ranking, which is by cost alone.",
  },
];

export default async function HomePage({ searchParams }: { searchParams: Promise<{ amount?: string }> }) {
  if (await getSessionUserId()) redirect("/dashboard");

  const { amount: rawAmount } = await searchParams;
  const amount = AMOUNTS.includes(Number(rawAmount)) ? Number(rawAmount) : 1_00_000;
  // Read before after(): request APIs are not available inside its callback.
  const campaign = await readCampaign();
  after(() => track("landing_viewed", { amount, ...campaign }));

  const [all, dates] = await Promise.all([getAllBrokers(), latestTradeDates(1)]);
  const rankable = all.filter((b) => b.feeScheduleComplete);
  const rankAt = (value: number) =>
    rankBrokersForFills(
      [
        { side: "BUY", fillPrice: value, qty: 1 },
        { side: "SELL", fillPrice: value, qty: 1 },
      ],
      rankable.map(toReplayBroker),
    );
  const ranked = rankAt(amount);
  // The hero always shows the ₹1 lakh case, whatever size the table is set to.
  const heroRanked = amount === 1_00_000 ? ranked : rankAt(1_00_000);
  const cheapest = heroRanked[0];
  // Structured data mirrors what the page shows: a free web app and its FAQ.
  const jsonLd = JSON.stringify({
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebApplication",
        name: SITE_NAME,
        url: `${APP_URL}/`,
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        isAccessibleForFree: true,
        offers: { "@type": "Offer", price: "0", priceCurrency: "INR" },
        inLanguage: "en-IN",
        publisher: { "@type": "Organization", name: "BrokerLens", url: "https://www.brokerlens.in/" },
      },
      {
        "@type": "FAQPage",
        mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
      },
    ],
  }).replace(/</g, "\\u003c");
  const dearest = heroRanked[heroRanked.length - 1];

  return (
    <>
      <AppHeader signedIn={false} />
      <main className="flex-1">
        <section className="border-b border-line bg-raised">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:py-20">
            <div>
              <p className="text-sm font-medium text-accent-ink">Virtual trading for Indian investors</p>
              <h1 className="mt-2 text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
                Practise investing. Find out what every broker would really charge you.
              </h1>
              <p className="mt-4 max-w-xl text-lg text-muted">
                Trade with ₹10 lakh of virtual cash at real NSE closing prices, with real brokerage and every tax applied.
                Then replay your own trades at {rankable.length} brokers to see who is cheapest for how you invest.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link href="/sign-up" className={cx(buttonClass("primary"), "px-6 py-3 text-base")}>
                  Start practising free
                </Link>
                <a href="#compare" className={cx(buttonClass("secondary"), "px-6 py-3 text-base")}>
                  Compare broker costs
                </a>
              </div>
              <p className="mt-4 text-xs text-muted">
                No real money, no exchange orders, no account opened. Prices are official NSE closes, never live
                prices.
              </p>
            </div>

            <div className="rounded-2xl border border-line bg-sub p-6">
              <div className="text-xs font-medium uppercase tracking-wide text-muted">Same ₹1 lakh buy and sell</div>
              <div className="mt-4 flex flex-col gap-4">
                {[cheapest, dearest].filter(Boolean).map((r, i) => (
                  <div key={r.id} className="flex items-center justify-between gap-4 rounded-xl bg-raised p-4">
                    <div>
                      <div className="text-sm text-muted">{i === 0 ? "Lowest" : "Highest"} of {heroRanked.length}</div>
                      <div className="font-semibold text-ink">{r.brand}</div>
                    </div>
                    <div className={cx("num text-2xl font-semibold", i === 0 ? "text-up" : "text-down")}>
                      {inr(r.totalCharges)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-5 text-xs font-medium uppercase tracking-wide text-muted">The broker&apos;s own share</div>
              <ul className="mt-2 flex flex-col gap-1.5" aria-label={`Brokerage plus DP charge at all ${heroRanked.length} brokers`}>
                {heroRanked.map((r) => {
                  // Zero-based so bar lengths are proportional to the rupees;
                  // a baseline offset would make small gaps look dramatic.
                  const own = r.brokerage + r.dpCharges;
                  const maxOwn = Math.max(...heroRanked.map((x) => x.brokerage + x.dpCharges)) || 1;
                  return (
                    <li key={r.id} className="grid grid-cols-[6.5rem_1fr_4rem] items-center gap-2 text-xs">
                      <span className="truncate text-muted">{r.brand}</span>
                      <span className="h-1.5 rounded-full bg-line">
                        <span
                          className={cx("block h-full rounded-full", r.rank === 1 ? "bg-up" : "bg-accent/70")}
                          style={{ width: `${Math.max(2, (own / maxOwn) * 100)}%` }}
                        />
                      </span>
                      <span className="num text-right text-ink">{inr(own)}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-4 text-sm text-muted">
                Same trade, same statutory taxes at every broker. What differs is the broker&apos;s own brokerage and DP
                charge (shown above, before GST), and which broker is cheapest changes with order size.
              </p>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">How it works</h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-xl border border-line bg-raised p-5">
                <div className="num flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink">
                  {i + 1}
                </div>
                <h3 className="mt-3 font-semibold text-ink">{s.title}</h3>
                <p className="mt-1 text-sm text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="compare" className="scroll-mt-24 border-t border-line bg-raised">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-ink">What a buy and sell costs at each broker</h2>
                <p className="mt-1 text-sm text-muted">
                  Equity delivery, buy and later sell the same value. All-in: brokerage, DP charge, STT, exchange and SEBI fees,
                  stamp duty and GST.
                </p>
              </div>
              <div role="group" aria-label="Order size" className="flex flex-wrap gap-1.5">
                {AMOUNTS.map((a) => (
                  <Link
                    key={a}
                    href={`/?amount=${a}#compare`}
                    scroll={false}
                    aria-current={a === amount ? "true" : undefined}
                    className={cx(
                      "num rounded-full border px-3 py-1.5 text-sm",
                      a === amount ? "border-accent bg-accent text-invert" : "border-line text-muted hover:border-accent hover:text-accent-ink",
                    )}
                  >
                    {inrWhole(a)}
                  </Link>
                ))}
              </div>
            </div>
            <div className="mt-6">
              <RankingTable rows={ranked} brokers={new Map(all.map((b) => [b.id, b]))} placement="landing" />
            </div>
            <p className="mt-3 text-xs text-muted">
              Ranked across the {ranked.length} brokers whose full fee schedule BrokerLens holds, by cost alone.
              {dates[0] ? ` Practice prices currently run to the ${shortDate(dates[0])} NSE close.` : ""}
            </p>

            <div className="mt-10 flex flex-col items-start justify-between gap-4 rounded-2xl bg-accent p-6 text-invert sm:flex-row sm:items-center">
              <div>
                <h3 className="text-lg font-semibold">The cheapest broker depends on how you trade.</h3>
                <p className="text-sm opacity-90">Practise for free and replay your own trades at every broker.</p>
              </div>
              <Link href="/sign-up" className="rounded-lg bg-raised px-5 py-2.5 text-sm font-semibold text-accent-ink hover:bg-hover">
                Start practising free
              </Link>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">Questions</h2>
          <div className="mt-6 flex flex-col divide-y divide-line rounded-xl border border-line bg-raised">
            {FAQ.map((f) => (
              <details key={f.q} className="group px-5 py-4">
                <summary className="cursor-pointer list-none font-medium text-ink marker:hidden">{f.q}</summary>
                <p className="mt-2 text-sm text-muted">{f.a}</p>
              </details>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted">
            The full rules for orders, fills, intraday and charges are on{" "}
            <Link href="/how-it-works" className="text-accent-ink underline-offset-2 hover:underline">
              How it works
            </Link>
            .
          </p>
        </section>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd }} />
      </main>
      <SiteFooter />
    </>
  );
}

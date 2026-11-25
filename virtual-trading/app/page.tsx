import Link from "next/link";
import { redirect } from "next/navigation";
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
    title: "Trade Nifty 100 stocks with ₹10 lakh of virtual cash",
    body: "See every charge before you place an order. It fills at the next official NSE close, never instantly.",
  },
  {
    title: "Replay your trades at every broker",
    body: "Find out which broker would actually have charged you least for the way you trade, before you open a real account.",
  },
];

export default async function HomePage({ searchParams }: { searchParams: Promise<{ amount?: string }> }) {
  if (await getSessionUserId()) redirect("/dashboard");

  const { amount: rawAmount } = await searchParams;
  const amount = AMOUNTS.includes(Number(rawAmount)) ? Number(rawAmount) : 1_00_000;

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
                No real money, no exchange orders, no account opened. Prices are official closes, delayed by a day for
                investor education.
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
      </main>
      <SiteFooter />
    </>
  );
}

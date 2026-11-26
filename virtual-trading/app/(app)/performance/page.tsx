import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getAccountSummary } from "@/lib/account-summary";
import { getSnapshots } from "@/lib/snapshots";
import { benchmarkPoints, getIndexSeries } from "@/lib/index-data";
import { MIN_TRADES_FOR_SCORE } from "@/lib/scoring";
import { inr, signedInr, signedPct, pnlTone } from "@/lib/format";
import { EquityChart } from "@/components/EquityChart";
import { buttonClass, Card, CardTitle, cx, PageHeader, Stat } from "@/components/ui";

export const metadata: Metadata = { title: "Performance" };

function term(n: number): string {
  const r = Math.round(n * 10) / 10;
  if (r === 0) return "0";
  return r > 0 ? `+${r}` : `${r}`;
}

export default async function PerformancePage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  const [s, snapshots] = await Promise.all([getAccountSummary(current.account), getSnapshots(current.account.id)]);
  if (!s) redirect("/onboarding/broker");

  // Prices are delayed, so a snapshot's trade date can be earlier than the
  // day the account was opened; start the curve at whichever comes first.
  const createdOn = current.account.createdAt.toISOString().slice(0, 10);
  const startDate = snapshots[0] && snapshots[0].snapshotDate < createdOn ? snapshots[0].snapshotDate : createdOn;
  const points = [
    { date: startDate, value: s.startingBalance },
    ...snapshots.map((p) => ({ date: p.snapshotDate, value: Number(p.portfolioValue) })),
  ];
  const benchmark = benchmarkPoints(
    points.map((p) => p.date),
    await getIndexSeries("nifty50", startDate),
    s.startingBalance,
  );
  const { score, label, enoughTrades, components: c } = s.score;
  const costDrag = s.turnoverTraded > 0 ? (s.chargesPaid / s.turnoverTraded) * 100 : null;

  return (
    <>
      <PageHeader title="Performance" subtitle="Measured only from your own simulated history on this account." />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <CardTitle action={<span className={cx("num text-sm font-medium", pnlTone(s.totalReturnPct))}>{signedPct(s.totalReturnPct)}</span>}>
            Portfolio value
          </CardTitle>
          <div className="num mb-3 text-3xl font-semibold text-ink">{inr(s.portfolioValue)}</div>
          <EquityChart points={points} startingBalance={s.startingBalance} benchmark={benchmark ? { label: "Nifty 50", points: benchmark } : null} />
        </Card>

        <Card>
          <CardTitle>Confidence score</CardTitle>
          {enoughTrades ? (
            <div className="flex items-baseline gap-3">
              <span className="num text-5xl font-semibold text-ink">{score}</span>
              <span className="text-sm font-medium text-accent-ink">{label}</span>
            </div>
          ) : (
            <div>
              <div className="text-lg font-semibold text-ink">Not enough trades yet</div>
              <p className="mt-1 text-sm text-muted">
                Close {MIN_TRADES_FOR_SCORE - s.closedTrades} more {MIN_TRADES_FOR_SCORE - s.closedTrades === 1 ? "trade" : "trades"} (buy, then sell)
                for a score that reflects more than one lucky or unlucky result.
              </p>
            </div>
          )}
          <dl className="mt-5 grid grid-cols-[1fr_auto] gap-y-1.5 border-t border-line pt-4 text-sm">
            <dt className="text-muted">Starting point</dt>
            <dd className="num text-right text-ink">{c.base}</dd>
            <dt className="text-muted">Return ({signedPct(s.totalReturnPct)}, capped at 25%)</dt>
            <dd className="num text-right text-ink">{term(c.returnTerm)}</dd>
            <dt className="text-muted">Win rate {s.winRate !== null ? `(${Math.round(s.winRate * 100)}%)` : `(after ${MIN_TRADES_FOR_SCORE} trades)`}</dt>
            <dd className="num text-right text-ink">{term(c.consistencyTerm)}</dd>
            <dt className="text-muted">Concentration in one stock</dt>
            <dd className="num text-right text-ink">{term(-c.concentrationPenalty)}</dd>
            <dt className="text-muted">Experience ({s.closedTrades} of 20 trades)</dt>
            <dd className="num text-right text-ink">{term(c.experienceBonus)}</dd>
          </dl>
          <p className="mt-4 text-xs text-muted">
            It rewards consistency and spreading risk, not just big returns. It is not a prediction of future results or
            investment advice.
          </p>
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Realized P&L" value={signedInr(s.realizedPnl)} tone={pnlTone(s.realizedPnl)} sub="After all charges" />
        <Stat label="Closed trades" value={s.closedTrades} sub={s.winRate !== null ? `${Math.round(s.winRate * 100)}% were profitable` : "Win rate after 5"} />
        <Stat label="Charges paid" value={inr(s.chargesPaid)} sub={`${s.ordersFilled} filled orders`} />
        <Stat label="Cost drag" value={costDrag !== null ? `${costDrag.toFixed(2)}%` : "-"} sub="Charges as a share of value traded" />
      </div>

      <Card className="mt-6 flex flex-wrap items-center justify-between gap-4 bg-accent-soft">
        <div>
          <h2 className="font-semibold text-ink">Would another broker have charged you less?</h2>
          <p className="text-sm text-muted">Replay every order you have filled at each fully documented broker.</p>
        </div>
        <Link href="/costs" className={buttonClass("primary")}>
          Open the cost replay
        </Link>
      </Card>
    </>
  );
}

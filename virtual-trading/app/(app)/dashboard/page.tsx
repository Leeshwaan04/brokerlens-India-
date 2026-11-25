import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getAccountSummary } from "@/lib/account-summary";
import { getRankableBrokers } from "@/lib/brokers";
import { latestTradeDates } from "@/lib/prices";
import { inr, shortDate, signedInr, signedPct, pnlTone } from "@/lib/format";
import { PendingOrders } from "@/components/PendingOrders";
import { ReadinessCard } from "@/components/ReadinessCard";
import { CostInsightCard } from "@/components/CostInsightCard";
import { buttonClass, Card, CardTitle, cx, PageHeader, Stat } from "@/components/ui";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const [summary, rankable, dates] = await Promise.all([
    getAccountSummary(current.account),
    getRankableBrokers(),
    latestTradeDates(1),
  ]);
  if (!summary) redirect("/onboarding/broker");
  const s = summary;
  const isNew = s.ordersPlaced === 0;

  return (
    <>
      <PageHeader
        title="Your portfolio"
        subtitle={dates[0] ? `Valued at the ${shortDate(dates[0])} NSE close` : "Waiting for the first NSE close to be ingested"}
        action={
          <Link href="/trade" className={buttonClass("primary")}>
            Place an order
          </Link>
        }
      />

      {isNew && (
        <Card className="mb-6 border-accent/30 bg-accent-soft">
          <h2 className="text-lg font-semibold text-ink">Start with one order</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            You have {inr(s.cash)} of virtual cash and {s.broker.brand}&apos;s real fee schedule. Pick a stock, see exactly
            what the order will cost before you place it, and it fills against the next session's official NSE prices.
          </p>
          <Link href="/trade" className={cx(buttonClass("primary"), "mt-4")}>
            Choose a stock
          </Link>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat
          label="Portfolio value"
          value={inr(s.portfolioValue)}
          sub={<span className={pnlTone(s.totalReturnPct)}>{signedPct(s.totalReturnPct)} since you started</span>}
        />
        <Stat
          label="Free cash"
          value={inr(s.availableCash)}
          sub={s.reservedCash > 0 ? `${inr(s.reservedCash)} held for pending buys` : "Available for new orders"}
        />
        <Stat label="Invested" value={inr(s.holdingsValue)} sub={`${s.holdings.length} ${s.holdings.length === 1 ? "stock" : "stocks"}`} />
        <Stat label="Unrealized P&L" value={signedInr(s.unrealizedPnl)} tone={pnlTone(s.unrealizedPnl)} sub="On shares you still hold" />
        <Stat
          label="Realized P&L"
          value={signedInr(s.realizedPnl)}
          tone={pnlTone(s.realizedPnl)}
          sub={`From ${s.closedTrades} closed ${s.closedTrades === 1 ? "trade" : "trades"}, after charges`}
        />
        <Stat
          label="Charges paid"
          value={inr(s.chargesPaid)}
          sub={s.turnoverTraded > 0 ? `${((s.chargesPaid / s.turnoverTraded) * 100).toFixed(2)}% of the value you traded` : "Brokerage, taxes and fees"}
        />
      </div>

      {s.pending.length > 0 && (
        <Card className="mt-6">
          <CardTitle action={<Link href="/orders" className="text-sm text-accent-ink hover:underline">All orders</Link>}>
            Waiting for the next close
          </CardTitle>
          <PendingOrders orders={s.pending} />
        </Card>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ReadinessCard milestones={s.milestones} progress={s.readiness} brokerId={s.broker.id} brokerBrand={s.broker.brand} />
        <CostInsightCard summary={s} rankable={rankable} />
      </div>

      {s.holdings.length > 0 && (
        <Card className="mt-6">
          <CardTitle action={<Link href="/portfolio" className="text-sm text-accent-ink hover:underline">All holdings</Link>}>
            Top holdings
          </CardTitle>
          <ul className="divide-y divide-line">
            {s.holdings.slice(0, 5).map((h) => (
              <li key={h.symbol} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <Link href={`/trade?symbol=${h.symbol}`} className="font-medium text-ink hover:text-accent-ink">
                    {h.symbol}
                  </Link>
                  <div className="truncate text-xs text-muted">
                    <span className="num">{h.qty}</span> shares · {h.name}
                  </div>
                </div>
                <div className="text-right">
                  <div className="num text-sm text-ink">{inr(h.marketValue)}</div>
                  <div className={cx("num text-xs", pnlTone(h.unrealizedPnl))}>
                    {h.unrealizedPnl !== null ? signedInr(h.unrealizedPnl) : "-"}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

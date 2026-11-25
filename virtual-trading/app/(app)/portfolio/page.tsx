import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getValuedHoldings, largestWeight, totalHoldingsValue, totalUnrealizedPnl } from "@/lib/portfolio";
import { inr, shortDate, signedInr, signedPct, pnlTone } from "@/lib/format";
import { DIVERSIFIED_MAX_WEIGHT } from "@/lib/readiness";
import { buttonClass, Card, cx, Notice, PageHeader, Stat } from "@/components/ui";

export const metadata: Metadata = { title: "Holdings" };

export default async function PortfolioPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const holdings = await getValuedHoldings(current.account.id);
  const value = totalHoldingsValue(holdings);
  const costBasis = holdings.reduce((s, h) => s + h.avgCost * h.qty, 0);
  const unrealized = totalUnrealizedPnl(holdings);
  const unrealizedPct = costBasis > 0 ? (unrealized / costBasis) * 100 : 0;
  const top = holdings[0];
  const topWeight = largestWeight(holdings);
  const asOf = holdings.find((h) => h.lastCloseDate)?.lastCloseDate;

  if (holdings.length === 0) {
    return (
      <>
        <PageHeader title="Holdings" />
        <Card className="text-center">
          <p className="text-muted">You do not hold any stocks yet. Filled buy orders appear here.</p>
          <Link href="/trade" className={cx(buttonClass("primary"), "mt-4")}>
            Place a buy order
          </Link>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Holdings" subtitle={asOf ? `Valued at the ${shortDate(asOf)} NSE close` : undefined} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Current value" value={inr(value)} />
        <Stat label="Cost (with charges)" value={inr(costBasis)} />
        <Stat label="Unrealized P&L" value={signedInr(unrealized)} tone={pnlTone(unrealized)} sub={<span className={pnlTone(unrealizedPct)}>{signedPct(unrealizedPct)}</span>} />
        <Stat label="Stocks" value={holdings.length} />
      </div>

      {topWeight !== null && topWeight > DIVERSIFIED_MAX_WEIGHT && top && (
        <div className="mt-4">
          <Notice tone="warn">
            {top.symbol} is {Math.round(topWeight * 100)}% of what you have invested. With that much in one company, its
            results move your whole portfolio. This is an observation about concentration, not a recommendation.
          </Notice>
        </div>
      )}

      <div className="mt-6 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-sub text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Stock</th>
              <th className="px-4 py-3 text-right font-medium">Qty</th>
              <th className="px-4 py-3 text-right font-medium">Avg. cost</th>
              <th className="px-4 py-3 text-right font-medium">Last close</th>
              <th className="px-4 py-3 text-right font-medium">Value</th>
              <th className="px-4 py-3 font-medium">Weight</th>
              <th className="px-4 py-3 text-right font-medium">Unrealized P&amp;L</th>
              <th className="px-4 py-3">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line bg-raised">
            {holdings.map((h) => {
              const weight = value > 0 ? h.marketValue / value : 0;
              const pct = h.unrealizedPnl !== null && h.avgCost > 0 ? (h.unrealizedPnl / (h.avgCost * h.qty)) * 100 : null;
              return (
                <tr key={h.symbol}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{h.symbol}</div>
                    <div className="max-w-[220px] truncate text-xs text-muted">{h.name}</div>
                  </td>
                  <td className="num px-4 py-3 text-right text-ink">{h.qty}</td>
                  <td className="num px-4 py-3 text-right text-ink">{inr(h.avgCost)}</td>
                  <td className="num px-4 py-3 text-right text-ink">{h.lastClose !== null ? inr(h.lastClose) : "-"}</td>
                  <td className="num px-4 py-3 text-right font-medium text-ink">{inr(h.marketValue)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-sub">
                        <div className={cx("h-full rounded-full", weight > DIVERSIFIED_MAX_WEIGHT ? "bg-warn" : "bg-accent")} style={{ width: `${Math.round(weight * 100)}%` }} />
                      </div>
                      <span className="num text-xs text-muted">{Math.round(weight * 100)}%</span>
                    </div>
                  </td>
                  <td className={cx("num px-4 py-3 text-right", pnlTone(h.unrealizedPnl))}>
                    {h.unrealizedPnl !== null ? signedInr(h.unrealizedPnl) : "-"}
                    {pct !== null && <div className="text-xs">{signedPct(pct)}</div>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Link href={`/trade?symbol=${h.symbol}`} className={buttonClass("secondary", "sm")}>
                        Buy more
                      </Link>
                      <Link href={`/trade?symbol=${h.symbol}&side=SELL`} className={buttonClass("danger", "sm")}>
                        Sell
                      </Link>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted">
        Average cost includes the buy-side charges you paid, so unrealized P&amp;L already reflects what the trades cost you.
      </p>
    </>
  );
}

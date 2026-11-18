import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { realizedPnlEvents } from "@/lib/schema";
import { getValuedHoldings, totalHoldingsValue } from "@/lib/portfolio";
import { computeConfidenceScore, MIN_TRADES_FOR_SCORE } from "@/lib/scoring";

function inr(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

export default async function PerformancePage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const { account } = current;
  const db = getDb();
  const closedTrades = await db.select().from(realizedPnlEvents).where(eq(realizedPnlEvents.accountId, account.id));

  const valuedHoldings = await getValuedHoldings(account.id);
  const holdingsValue = totalHoldingsValue(valuedHoldings);
  const cashBalance = Number(account.cashBalance);
  const portfolioValue = cashBalance + holdingsValue;
  const startingBalance = Number(account.startingBalance);
  const totalReturnPct = startingBalance > 0 ? ((portfolioValue - startingBalance) / startingBalance) * 100 : 0;

  const numClosedTrades = closedTrades.length;
  const wins = closedTrades.filter((t) => Number(t.realizedPnl) > 0).length;
  const winRate = numClosedTrades >= MIN_TRADES_FOR_SCORE ? wins / numClosedTrades : null;
  const largestHoldingValue = valuedHoldings.reduce((max, h) => Math.max(max, h.marketValue), 0);

  const { score, label, enoughTrades } = computeConfidenceScore({
    totalReturnPct,
    numClosedTrades,
    winRate,
    largestHoldingValue,
    portfolioValue,
  });

  return (
    <main className="mx-auto max-w-2xl flex-1 p-8">
      <h1 className="mb-6 text-2xl font-semibold">Performance</h1>

      <div className="mb-8 rounded-lg border p-6 text-center">
        {enoughTrades ? (
          <>
            <div className="text-4xl font-semibold">{score}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
          </>
        ) : (
          <>
            <div className="text-lg font-medium">Not enough trades yet</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Close at least {MIN_TRADES_FOR_SCORE} trades (buy, then sell) to get a confidence score.
            </div>
          </>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-gray-500">Total return</dt>
          <dd className={totalReturnPct >= 0 ? "text-green-600" : "text-red-600"}>
            {totalReturnPct >= 0 ? "+" : ""}
            {totalReturnPct.toFixed(2)}%
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">Closed trades</dt>
          <dd>{numClosedTrades}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Win rate</dt>
          <dd>{winRate !== null ? `${(winRate * 100).toFixed(0)}%` : "-"}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Portfolio value</dt>
          <dd>{inr(portfolioValue)}</dd>
        </div>
      </dl>

      <p className="mt-8 text-xs text-gray-500">
        This score reflects only your own simulated trade history on this account. It is not a prediction
        of future results and is not investment advice.
      </p>
    </main>
  );
}

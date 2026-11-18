import { redirect } from "next/navigation";
import Link from "next/link";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog } from "@/lib/schema";
import { getValuedHoldings, totalHoldingsValue, totalUnrealizedPnl } from "@/lib/portfolio";

function inr(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

export default async function DashboardPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const { account } = current;
  const db = getDb();
  const [broker] = await db.select().from(brokerCatalog).where(eq(brokerCatalog.id, account.brokerId)).limit(1);

  const valuedHoldings = await getValuedHoldings(account.id);
  const cashBalance = Number(account.cashBalance);
  const holdingsValue = totalHoldingsValue(valuedHoldings);
  const unrealizedPnl = totalUnrealizedPnl(valuedHoldings);
  const portfolioValue = cashBalance + holdingsValue;
  const startingBalance = Number(account.startingBalance);
  const totalReturnPct = startingBalance > 0 ? ((portfolioValue - startingBalance) / startingBalance) * 100 : 0;

  return (
    <main className="mx-auto max-w-4xl flex-1 p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <span className="text-sm text-gray-600 dark:text-gray-400">
          Broker: {broker?.brand ?? account.brokerId}
        </span>
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500">Portfolio value</div>
          <div className="text-xl font-semibold">{inr(portfolioValue)}</div>
          <div className={totalReturnPct >= 0 ? "text-sm text-green-600" : "text-sm text-red-600"}>
            {totalReturnPct >= 0 ? "+" : ""}
            {totalReturnPct.toFixed(2)}% since start
          </div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500">Cash balance</div>
          <div className="text-xl font-semibold">{inr(cashBalance)}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-gray-500">Unrealized P&amp;L</div>
          <div className={unrealizedPnl >= 0 ? "text-xl font-semibold text-green-600" : "text-xl font-semibold text-red-600"}>
            {inr(unrealizedPnl)}
          </div>
        </div>
      </div>

      <div className="flex gap-4">
        <Link href="/trade" className="rounded-md bg-black px-4 py-2 text-white dark:bg-white dark:text-black">
          Place an order
        </Link>
        <Link href="/portfolio" className="rounded-md border px-4 py-2">
          View holdings
        </Link>
        <Link href="/orders" className="rounded-md border px-4 py-2">
          Order history
        </Link>
      </div>

      <p className="mt-8 text-xs text-gray-500">
        Prices here are delayed, official NSE closes, for investor education, not live market data. Orders
        fill at the next available close, not instantly.
      </p>
    </main>
  );
}

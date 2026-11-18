import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getValuedHoldings } from "@/lib/portfolio";

function inr(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

export default async function PortfolioPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const valuedHoldings = await getValuedHoldings(current.account.id);

  return (
    <main className="mx-auto max-w-4xl flex-1 p-8">
      <h1 className="mb-6 text-2xl font-semibold">Holdings</h1>
      {valuedHoldings.length === 0 ? (
        <p className="text-sm text-gray-600">No open positions.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-4">Symbol</th>
              <th className="py-2 pr-4">Qty</th>
              <th className="py-2 pr-4">Avg. cost</th>
              <th className="py-2 pr-4">Last close</th>
              <th className="py-2 pr-4">Market value</th>
              <th className="py-2 pr-4">Unrealized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {valuedHoldings.map((h) => (
              <tr key={h.symbol} className="border-b">
                <td className="py-2 pr-4 font-medium">{h.symbol}</td>
                <td className="py-2 pr-4">{h.qty}</td>
                <td className="py-2 pr-4">{inr(h.avgCost)}</td>
                <td className="py-2 pr-4">{h.lastClose !== null ? inr(h.lastClose) : "-"}</td>
                <td className="py-2 pr-4">{inr(h.marketValue)}</td>
                <td className={`py-2 pr-4 ${(h.unrealizedPnl ?? 0) >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {h.unrealizedPnl !== null ? inr(h.unrealizedPnl) : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

import { redirect } from "next/navigation";
import { eq, desc } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { orders } from "@/lib/schema";

function inr(v: string | null): string {
  if (v === null) return "-";
  return Number(v).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

export default async function OrdersPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const db = getDb();
  const rows = await db
    .select()
    .from(orders)
    .where(eq(orders.accountId, current.account.id))
    .orderBy(desc(orders.requestedAt));

  return (
    <main className="mx-auto max-w-5xl flex-1 p-8">
      <h1 className="mb-6 text-2xl font-semibold">Order history</h1>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-600">No orders yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2 pr-4">Symbol</th>
                <th className="py-2 pr-4">Side</th>
                <th className="py-2 pr-4">Qty</th>
                <th className="py-2 pr-4">Target date</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Fill price</th>
                <th className="py-2 pr-4">Total charges</th>
                <th className="py-2 pr-4">Net amount</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} className="border-b align-top">
                  <td className="py-2 pr-4 font-medium">{o.symbol}</td>
                  <td className="py-2 pr-4">{o.side}</td>
                  <td className="py-2 pr-4">{o.qty}</td>
                  <td className="py-2 pr-4">{o.targetTradeDate}</td>
                  <td className="py-2 pr-4">
                    {o.status}
                    {o.status === "REJECTED" && o.rejectionReason && (
                      <div className="text-xs text-red-600">{o.rejectionReason.replaceAll("_", " ")}</div>
                    )}
                  </td>
                  <td className="py-2 pr-4">{o.fillPrice ? inr(o.fillPrice) : "-"}</td>
                  <td className="py-2 pr-4">
                    {o.totalCharges ? (
                      <details>
                        <summary className="cursor-pointer">{inr(o.totalCharges)}</summary>
                        <div className="mt-1 text-xs text-gray-500">
                          Brokerage {inr(o.brokerage)} &middot; STT {inr(o.stt)} &middot; Exchange{" "}
                          {inr(o.exchangeCharges)} &middot; SEBI {inr(o.sebiCharges)} &middot; Stamp duty{" "}
                          {inr(o.stampDuty)} &middot; GST {inr(o.gst)} &middot; DP {inr(o.dpCharge)}
                        </div>
                      </details>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="py-2 pr-4">{o.netAmount ? inr(o.netAmount) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

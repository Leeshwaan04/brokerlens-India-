import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { desc, eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { orders, stockUniverse } from "@/lib/schema";
import { inr, pnlTone, shortDate, signedInr } from "@/lib/format";
import { EXIT_REASON_LABEL, orderTermsLabel } from "@/lib/fills";
import { PendingOrders } from "@/components/PendingOrders";
import { FillRules } from "@/components/FillRules";
import { buttonClass, Card, CardTitle, cx, PageHeader, Pill } from "@/components/ui";

export const metadata: Metadata = { title: "Orders" };

const REJECTION_TEXT: Record<string, string> = {
  insufficient_funds_at_settlement: "Not enough cash on the fill date at the actual closing price",
  insufficient_holdings_at_settlement: "Not enough shares held on the fill date",
  corporate_action: "Cancelled on a split or bonus ex-date, as brokers cancel open orders when the share count changes",
  expired: "Its price was not reached during the session, so the day order ended",
  gtt_expired: "Its price was not reached within a year, so the GTT order ended",
  insufficient_margin_at_settlement: "Not enough cash for the intraday margin on the session date",
};

function money(v: string | null): string {
  return v === null ? "-" : inr(Number(v));
}

const STATUS_TONE = { FILLED: "up", PENDING: "info", REJECTED: "down", CANCELLED: "neutral" } as const;

export default async function OrdersPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const rows = await getDb()
    .select({ order: orders, name: stockUniverse.name })
    .from(orders)
    .innerJoin(stockUniverse, eq(orders.symbol, stockUniverse.symbol))
    .where(eq(orders.accountId, current.account.id))
    .orderBy(desc(orders.requestedAt));

  const pending = rows.filter((r) => r.order.status === "PENDING");
  const history = rows.filter((r) => r.order.status !== "PENDING");

  if (rows.length === 0) {
    return (
      <>
        <PageHeader title="Orders" />
        <Card className="text-center">
          <p className="text-muted">No orders yet. Every order you place shows here, with its full cost breakdown once it fills.</p>
          <Link href="/trade" className={cx(buttonClass("primary"), "mt-4")}>
            Place your first order
          </Link>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Orders"
        subtitle="Each order is checked against its practice-market session's official open, high, low and close. How fills work is set out below."
        action={
          <a href="/api/reports/statement" className={buttonClass("secondary", "sm")}>
            Download statement (Plus)
          </a>
        }
      />

      {pending.length > 0 && (
        <Card className="mb-6">
          <CardTitle>Open orders</CardTitle>
          <PendingOrders
            orders={pending.map((r) => ({
              id: r.order.id,
              symbol: r.order.symbol,
              name: r.name,
              side: r.order.side,
              qty: r.order.qty,
              targetTradeDate: r.order.targetTradeDate,
              orderType: r.order.orderType,
              limitPrice: r.order.limitPrice,
              triggerPrice: r.order.triggerPrice,
              validity: r.order.validity,
              beforeOpen: r.order.beforeOpen,
              expiresOn: r.order.expiresOn,
              product: r.order.product,
              stopLossPrice: r.order.stopLossPrice,
              targetPrice: r.order.targetPrice,
            }))}
          />
        </Card>
      )}

      {history.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-sub text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Session</th>
                <th className="px-4 py-3 font-medium">Stock</th>
                <th className="px-4 py-3 font-medium">Order</th>
                <th className="px-4 py-3 text-right font-medium">Qty</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Fill price</th>
                <th className="px-4 py-3 text-right font-medium">Charges</th>
                <th className="px-4 py-3 text-right font-medium">Cash in / out</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-raised">
              {history.map(({ order: o, name }) => (
                <tr key={o.id} className="align-top">
                  <td className="num whitespace-nowrap px-4 py-3 text-ink">{shortDate(o.targetTradeDate)}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{o.symbol}</div>
                    <div className="max-w-[200px] truncate text-xs text-muted">{name}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Pill tone={o.side === "BUY" ? "up" : "down"}>{o.side === "BUY" ? "Buy" : "Sell"}</Pill>
                    <div className="num mt-1 whitespace-nowrap text-xs text-muted">
                      {o.product === "MIS" ? "Intraday, " : ""}
                      {orderTermsLabel(o)}
                      {o.validity === "GTT" ? ", GTT" : ""}
                      {o.orderType === "MARKET" && o.beforeOpen ? ", at open" : ""}
                    </div>
                  </td>
                  <td className="num px-4 py-3 text-right text-ink">{o.qty}</td>
                  <td className="px-4 py-3">
                    <Pill tone={STATUS_TONE[o.status]}>{o.status.charAt(0) + o.status.slice(1).toLowerCase()}</Pill>
                    {(o.status === "REJECTED" || o.status === "CANCELLED") && o.rejectionReason && (
                      <div className="mt-1 max-w-[200px] text-xs text-down">{REJECTION_TEXT[o.rejectionReason] ?? o.rejectionReason.replaceAll("_", " ")}</div>
                    )}
                  </td>
                  <td className="num px-4 py-3 text-right text-ink">
                    {money(o.fillPrice)}
                    {o.product === "MIS" && o.exitPrice && (
                      <div className="whitespace-nowrap text-xs text-muted">
                        Exit {money(o.exitPrice)}
                        {o.exitReason ? `, ${EXIT_REASON_LABEL[o.exitReason].toLowerCase()}` : ""}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {o.totalCharges ? (
                      <details className="text-left">
                        <summary className="num cursor-pointer text-right text-ink">{money(o.totalCharges)}</summary>
                        <dl className="mt-2 grid min-w-[180px] grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-muted">
                          <dt>Brokerage</dt><dd className="num text-right">{money(o.brokerage)}</dd>
                          <dt>STT</dt><dd className="num text-right">{money(o.stt)}</dd>
                          <dt>Exchange</dt><dd className="num text-right">{money(o.exchangeCharges)}</dd>
                          <dt>SEBI</dt><dd className="num text-right">{money(o.sebiCharges)}</dd>
                          <dt>Stamp duty</dt><dd className="num text-right">{money(o.stampDuty)}</dd>
                          <dt>GST</dt><dd className="num text-right">{money(o.gst)}</dd>
                          <dt>DP</dt><dd className="num text-right">{money(o.dpCharge)}</dd>
                        </dl>
                      </details>
                    ) : (
                      <span className="text-muted">-</span>
                    )}
                  </td>
                  {o.product === "MIS" ? (
                    <td className={cx("num px-4 py-3 text-right", o.netAmount ? pnlTone(Number(o.netAmount)) : "text-muted")}>
                      {o.netAmount ? signedInr(Number(o.netAmount)) : "-"}
                      {o.netAmount && <div className="text-xs text-muted">P&amp;L after charges</div>}
                    </td>
                  ) : (
                    <td className={cx("num px-4 py-3 text-right", o.netAmount ? (o.side === "BUY" ? "text-down" : "text-up") : "text-muted")}>
                      {o.netAmount ? `${o.side === "BUY" ? "-" : "+"}${money(o.netAmount)}` : "-"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card className="mt-6">
        <h2 className="font-semibold text-ink">How fills work</h2>
        <FillRules />
      </Card>
    </>
  );
}

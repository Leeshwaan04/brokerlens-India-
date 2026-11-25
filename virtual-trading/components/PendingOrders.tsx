import { cancelOrderAction } from "@/app/(app)/actions";
import type { PendingOrderView } from "@/lib/account-summary";
import { nextChanceText, orderTermsLabel } from "@/lib/fills";
import { buttonClass, Pill } from "./ui";

export function PendingOrders({ orders, compact = false }: { orders: PendingOrderView[]; compact?: boolean }) {
  if (orders.length === 0) return null;
  return (
    <ul className="divide-y divide-line">
      {orders.map((o) => (
        <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Pill tone={o.side === "BUY" ? "up" : "down"}>{o.side === "BUY" ? "Buy" : "Sell"}</Pill>
              <span className="font-medium text-ink">
                <span className="num">{o.qty}</span> {o.symbol}
              </span>
              <span className="num text-xs text-muted">{orderTermsLabel(o)}</span>
              {o.beforeOpen && o.orderType === "MARKET" && <Pill tone="info">After-market</Pill>}
            </div>
            {!compact && <div className="mt-0.5 truncate text-xs text-muted">{o.name}</div>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">{nextChanceText(o)}</span>
            <form action={cancelOrderAction}>
              <input type="hidden" name="orderId" value={o.id} />
              <button type="submit" className={buttonClass("danger", "sm")}>
                Cancel
              </button>
            </form>
          </div>
        </li>
      ))}
    </ul>
  );
}

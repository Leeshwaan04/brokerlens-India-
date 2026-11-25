import type { ReactNode } from "react";
import type { BrokerRow } from "@/lib/brokers";
import { deliveryFeesFromRow, roundTripCharges } from "@/lib/trade-costs";
import { deliveryRuleText } from "@/lib/fee-text";
import { inr } from "@/lib/format";
import { Pill } from "./ui";

export const SAMPLE_TURNOVER = 1_00_000;

// Shared broker summary: name, badges, the delivery fee rule, DP charge and
// what a ₹1 lakh buy and sell would cost (the same worked example
// brokerlens.in publishes on every broker's charges page).
export function BrokerCard({ broker, action }: { broker: BrokerRow; action?: ReactNode }) {
  const fees = deliveryFeesFromRow(broker);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-ink">{broker.brand}</div>
          {broker.tagline && <div className="text-xs text-muted">{broker.tagline}</div>}
        </div>
        {action}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {broker.feeScheduleComplete ? <Pill tone="up">Full fee schedule on file</Pill> : <Pill tone="warn">Indicative fees</Pill>}
        {broker.partnerBadge && <Pill tone="accent">Partner</Pill>}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
        <dt className="text-muted">Delivery</dt>
        <dd className="text-ink">{deliveryRuleText(fees)}</dd>
        <dt className="text-muted">DP charge</dt>
        <dd className="num text-ink">{inr(fees.dpCharge)} per sell</dd>
        <dt className="text-muted">₹1 lakh buy and sell</dt>
        <dd className="num font-medium text-ink">{inr(roundTripCharges(SAMPLE_TURNOVER, fees))} all-in</dd>
      </dl>
    </div>
  );
}

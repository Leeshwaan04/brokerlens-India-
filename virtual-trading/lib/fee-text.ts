import { CAP_RULE_MAX_PCT, type DeliveryFees } from "./trade-costs";
import { inr } from "./format";

function pctText(pct: number): string {
  return `${Number((pct * 100).toFixed(3))}%`;
}

/** Delivery brokerage rule in words, using the same cap logic as the fee math. */
export function deliveryRuleText(fees: DeliveryFees): string {
  const { deliveryFlat: flat, deliveryPct: pct, capVerified } = fees;
  if (!flat && !pct) return "Free delivery brokerage";
  if (pct > CAP_RULE_MAX_PCT && !capVerified) return `${pctText(pct)} of order value`;
  if (flat && pct) return `${inr(flat)} or ${pctText(pct)}, whichever is lower`;
  if (pct) return `${pctText(pct)} of order value`;
  return `${inr(flat)} per order`;
}

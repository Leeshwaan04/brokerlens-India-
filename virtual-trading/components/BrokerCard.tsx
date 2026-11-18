import type { ReactNode } from "react";
import type { brokerCatalog } from "@/lib/schema";

type BrokerRow = typeof brokerCatalog.$inferSelect;

// Shared broker card, used by the onboarding broker-selection page (with a
// radio input as `action`) and the broker detail/switch page (with no
// action, or a "Switch broker" action). Keeps both pages' broker summary in
// sync with a single source of truth instead of duplicating the markup.
export function BrokerCard({ broker, action }: { broker: BrokerRow; action?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center justify-between gap-3">
        <span className="font-medium">{broker.brand}</span>
        {action}
      </span>
      {broker.tagline && <span className="text-sm text-gray-600 dark:text-gray-400">{broker.tagline}</span>}
    </div>
  );
}

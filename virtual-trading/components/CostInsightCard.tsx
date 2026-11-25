import Link from "next/link";
import type { AccountSummary } from "@/lib/account-summary";
import { goHref, toReplayBroker, type BrokerRow } from "@/lib/brokers";
import { rankBrokersForFills, replayAtBroker } from "@/lib/cost-replay";
import { roundTripCharges } from "@/lib/trade-costs";
import { inr } from "@/lib/format";
import { SAMPLE_TURNOVER } from "./BrokerCard";
import { buttonClass, Card, CardTitle } from "./ui";

export function CostInsightCard({ summary, rankable }: { summary: AccountSummary; rankable: BrokerRow[] }) {
  const { broker, fees, fills } = summary;

  if (fills.length === 0) {
    const sample = rankable
      .map((b) => ({ id: b.id, brand: b.brand, cost: roundTripCharges(SAMPLE_TURNOVER, toReplayBroker(b).fees) }))
      .sort((a, b) => a.cost - b.cost || a.brand.localeCompare(b.brand));
    const yours = roundTripCharges(SAMPLE_TURNOVER, fees);
    return (
      <Card>
        <CardTitle>What brokers charge</CardTitle>
        <p className="text-sm text-muted">
          A ₹1 lakh buy and later sell costs <span className="num font-medium text-ink">{inr(yours)}</span> all-in at{" "}
          {broker.brand}. Cheapest of the {rankable.length} brokers with a full fee schedule:
        </p>
        <ol className="mt-3 flex flex-col gap-1.5 text-sm">
          {sample.slice(0, 3).map((s, i) => (
            <li key={s.id} className="flex justify-between gap-3">
              <span className="text-ink">
                <span className="num mr-2 text-muted">{i + 1}.</span>
                {s.brand}
              </span>
              <span className="num text-ink">{inr(s.cost)}</span>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs text-muted">Once your first orders fill, this becomes a replay of your own trades.</p>
        <Link href="/costs" className={`${buttonClass("ghost", "sm")} mt-2 -ml-3`}>
          See all brokers
        </Link>
      </Card>
    );
  }

  const ranked = rankBrokersForFills(fills, rankable.map(toReplayBroker));
  const yours = replayAtBroker(fills, fees);
  const cheapest = ranked[0];
  const saving = yours.totalCharges - cheapest.totalCharges;
  const isCheapest = cheapest.id === broker.id || saving < 0.5;

  return (
    <Card>
      <CardTitle>Your trades, at every broker</CardTitle>
      {isCheapest ? (
        <p className="text-sm text-ink">
          For your {fills.length} filled orders, {broker.brand} is already the cheapest of the {ranked.length} fully documented
          brokers, at <span className="num font-semibold">{inr(yours.totalCharges)}</span> in charges.
        </p>
      ) : (
        <>
          <p className="text-sm text-ink">
            Your {fills.length} filled orders cost <span className="num font-semibold">{inr(yours.totalCharges)}</span> at{" "}
            {broker.brand}. At <span className="font-semibold">{cheapest.brand}</span>, the cheapest of {ranked.length}, the
            same trades would have cost <span className="num font-semibold">{inr(cheapest.totalCharges)}</span>.
          </p>
          <div className="mt-3 rounded-lg bg-up-soft px-3 py-2 text-sm text-ink">
            That is <span className="num font-semibold">{inr(saving)}</span> less on the same trades.
          </div>
        </>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href="/costs" className={buttonClass("primary", "sm")}>
          See the full replay
        </Link>
        {!isCheapest && (
          <a href={goHref(cheapest.id, "dashboard")} target="_blank" rel="noopener sponsored nofollow" className={buttonClass("secondary", "sm")}>
            Open a {cheapest.brand} account
          </a>
        )}
      </div>
    </Card>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getAccountSummary } from "@/lib/account-summary";
import { getAllBrokers, toReplayBroker } from "@/lib/brokers";
import { rankBrokersForFills, replayAtBroker, type ReplayFill } from "@/lib/cost-replay";
import { inr } from "@/lib/format";
import { RankingTable } from "@/components/RankingTable";
import { AffiliateDisclosure, buttonClass, Card, Notice, PageHeader, Stat } from "@/components/ui";

export const metadata: Metadata = { title: "Broker cost replay" };

const SAMPLE_TURNOVER = 1_00_000;

export default async function CostsPage({ searchParams }: { searchParams: Promise<{ switched?: string }> }) {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  const [summary, allBrokers] = await Promise.all([getAccountSummary(current.account), getAllBrokers()]);
  if (!summary) redirect("/onboarding/broker");

  const { switched } = await searchParams;
  const byId = new Map(allBrokers.map((b) => [b.id, b]));
  const switchedTo = switched ? byId.get(switched) : undefined;

  // Rank only brokers whose full fee schedule is on file. If the practice
  // broker is not one of them, it still appears (marked indicative) so the
  // user can see where it sits, but it never takes a ranked "lowest" spot
  // on an incomplete schedule.
  const rankable = allBrokers.filter((b) => b.feeScheduleComplete);
  const hasFills = summary.fills.length > 0;
  const fills: ReplayFill[] = hasFills
    ? summary.fills
    : [
        { side: "BUY", fillPrice: SAMPLE_TURNOVER, qty: 1 },
        { side: "SELL", fillPrice: SAMPLE_TURNOVER, qty: 1 },
      ];

  const ranked = rankBrokersForFills(fills, rankable.map(toReplayBroker));
  const yours = replayAtBroker(fills, summary.fees);
  const currentRanked = ranked.some((r) => r.id === summary.broker.id);
  const rows = currentRanked
    ? ranked
    : [...ranked, { id: summary.broker.id, brand: summary.broker.brand, rank: ranked.length + 1, ...yours }];
  const cheapest = ranked[0];
  const saving = Math.max(0, yours.totalCharges - cheapest.totalCharges);
  const turnover = hasFills ? summary.turnoverTraded : SAMPLE_TURNOVER * 2;
  const savingPerLakh = turnover > 0 ? (saving / turnover) * 1_00_000 : 0;

  return (
    <>
      <PageHeader
        title="Broker cost replay"
        subtitle={
          hasFills
            ? `Your ${summary.fills.length} filled orders, re-priced under each broker's published delivery fees. Same prices, same quantities, only the fees change.`
            : "Once your orders fill, this replays them at every broker. Until then, here is a ₹1 lakh buy and later sell."
        }
      />

      {switchedTo && (
        <div className="mb-6">
          <Notice tone="up">
            You are now practising with {switchedTo.brand}. Your next orders will be costed with its fees; filled orders keep
            the charges they settled with.
          </Notice>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label={`At ${summary.broker.brand}`} value={inr(yours.totalCharges)} sub={hasFills ? "Your practice broker" : "₹1 lakh buy and sell"} />
        <Stat label={`Lowest: ${cheapest.brand}`} value={inr(cheapest.totalCharges)} sub={`Cheapest of ${ranked.length} fully documented brokers`} tone="text-up" />
        <Stat
          label="You could save"
          value={inr(saving)}
          tone={saving > 0.5 ? "text-up" : "text-muted"}
          sub={saving > 0.5 ? `About ${inr(savingPerLakh)} per ₹1 lakh traded` : "Your broker is already the cheapest"}
        />
      </div>

      {hasFills && Math.abs(summary.chargesPaid - yours.totalCharges) > 0.5 && (
        <p className="mt-3 text-xs text-muted">
          You actually paid {inr(summary.chargesPaid)}, because some orders settled while you practised with a different broker.
          The replay above prices all of them at {summary.broker.brand}.
        </p>
      )}

      <div className="mt-6">
        <RankingTable
          rows={rows}
          brokers={byId}
          placement="replay"
          currentId={summary.broker.id}
          baselineTotal={yours.totalCharges}
          allowSwitch
        />
      </div>

      {!hasFills && (
        <Card className="mt-6 bg-sub">
          <p className="text-sm text-muted">
            Flat-fee brokers cost the same on a ₹10,000 order as on a ₹10 lakh one, while percentage brokers scale with
            size, so the cheapest broker depends on how you trade. Your replay will show the answer for your own orders.
          </p>
          <Link href="/trade" className={`${buttonClass("primary", "sm")} mt-3`}>
            Place your first order
          </Link>
        </Card>
      )}

      <Card className="mt-6">
        <h2 className="font-semibold text-ink">How this is calculated</h2>
        <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted">
          <li>Each filled order is costed as an equity delivery order at its real fill price, one leg at a time.</li>
          <li>
            Statutory charges are the same at every broker: STT 0.1% on both legs, NSE transaction charges 0.00297%, SEBI
            fee ₹10 per crore, stamp duty 0.015% on buys, and GST 18% on brokerage and exchange and SEBI fees.
          </li>
          <li>DP charges apply once per sell order. Annual demat AMC is shown under each broker but not added to the totals.</li>
          <li>
            Only the {ranked.length} brokers whose full fee schedule BrokerLens holds are ranked. The order is by cost alone
            and never by partner status.
          </li>
          <li>Fees can change. Confirm current charges on the broker&apos;s own site before opening an account.</li>
        </ul>
        <div className="mt-4">
          <AffiliateDisclosure />
        </div>
      </Card>
    </>
  );
}

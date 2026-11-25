import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentAccount } from "@/lib/auth";
import { getAllBrokers, goHref, type BrokerRow } from "@/lib/brokers";
import { deliveryFeesFromRow, roundTripCharges } from "@/lib/trade-costs";
import { deliveryRuleText } from "@/lib/fee-text";
import { inr, shortDate } from "@/lib/format";
import { switchBrokerAction } from "../actions";
import { BrokerCard, SAMPLE_TURNOVER } from "@/components/BrokerCard";
import { AffiliateDisclosure, buttonClass, Card, CardTitle, Notice, PageHeader, Pill } from "@/components/ui";

export const metadata: Metadata = { title: "Your broker" };

function sample(b: BrokerRow): number {
  return roundTripCharges(SAMPLE_TURNOVER, deliveryFeesFromRow(b));
}

export default async function BrokerPage({ searchParams }: { searchParams: Promise<{ switched?: string }> }) {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const all = await getAllBrokers();
  const broker = all.find((b) => b.id === current.account!.brokerId);
  if (!broker) redirect("/onboarding/broker");
  const { switched } = await searchParams;
  const fees = deliveryFeesFromRow(broker);
  const others = all
    .filter((b) => b.id !== broker.id)
    .sort((a, b) => Number(b.feeScheduleComplete) - Number(a.feeScheduleComplete) || sample(a) - sample(b));

  return (
    <>
      <PageHeader title="Your practice broker" subtitle="Your virtual orders are costed with this broker's published fees." />

      {switched === broker.id && (
        <div className="mb-6">
          <Notice tone="up">
            Switched to {broker.brand}. New orders, and any still waiting to fill, will be costed with its fees.
          </Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold text-ink">{broker.brand}</h2>
            {broker.feeScheduleComplete ? <Pill tone="up">Full fee schedule on file</Pill> : <Pill tone="warn">Indicative fees</Pill>}
            {broker.partnerBadge && <Pill tone="accent">Partner</Pill>}
          </div>
          {broker.tagline && <p className="mt-1 text-sm text-muted">{broker.tagline}</p>}
          <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-muted">Equity delivery brokerage</dt>
            <dd className="text-ink">{deliveryRuleText(fees)}</dd>
            <dt className="text-muted">DP charge</dt>
            <dd className="num text-ink">{inr(fees.dpCharge)} per sell order</dd>
            {broker.dematAmc != null && (
              <>
                <dt className="text-muted">Demat AMC</dt>
                <dd className="num text-ink">{Number(broker.dematAmc) === 0 ? "None" : `${inr(Number(broker.dematAmc))} a year`}</dd>
              </>
            )}
            {broker.accountOpen != null && (
              <>
                <dt className="text-muted">Account opening</dt>
                <dd className="num text-ink">{Number(broker.accountOpen) === 0 ? "Free" : inr(Number(broker.accountOpen))}</dd>
              </>
            )}
            <dt className="text-muted">₹1 lakh buy and sell</dt>
            <dd className="num font-medium text-ink">{inr(sample(broker))} all-in</dd>
            {broker.capVerifiedAsof && (
              <>
                <dt className="text-muted">Cap verified</dt>
                <dd className="text-ink">Against the broker&apos;s own pricing page, {shortDate(broker.capVerifiedAsof)}</dd>
              </>
            )}
          </dl>
          <div className="mt-6 flex flex-wrap gap-2">
            <a href={goHref(broker.id, "broker")} target="_blank" rel="noopener sponsored nofollow" className={buttonClass("primary")}>
              Open a real {broker.brand} account
            </a>
            <Link href="/costs" className={buttonClass("secondary")}>
              Compare with other brokers
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted">
            These figures are what BrokerLens has on file, not a quote. Confirm current charges on {broker.brand}&apos;s own site
            before opening an account.
          </p>
          <div className="mt-3">
            <AffiliateDisclosure />
          </div>
        </Card>

        <Card>
          <CardTitle>Practise with a different broker</CardTitle>
          <p className="mb-4 text-sm text-muted">
            Switching only changes which fee schedule costs your orders from now on. Cash, holdings and filled orders stay as
            they are.
          </p>
          <ul className="flex max-h-[560px] flex-col gap-2 overflow-y-auto pr-1">
            {others.map((b) => (
              <li key={b.id} className="rounded-lg border border-line p-3">
                <BrokerCard
                  broker={b}
                  action={
                    <form action={switchBrokerAction}>
                      <input type="hidden" name="brokerId" value={b.id} />
                      <button type="submit" className={buttonClass("secondary", "sm")}>
                        Switch
                      </button>
                    </form>
                  }
                />
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

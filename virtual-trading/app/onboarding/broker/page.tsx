import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { ensureUserRow } from "@/lib/auth";
import { readCampaign, track } from "@/lib/events";
import { getSessionUserId } from "@/lib/session";
import { getDb } from "@/lib/db";
import { brokerCatalog, virtualAccounts } from "@/lib/schema";
import { getAllBrokers, type BrokerRow } from "@/lib/brokers";
import { deliveryFeesFromRow, roundTripCharges } from "@/lib/trade-costs";
import { BrokerCard, SAMPLE_TURNOVER } from "@/components/BrokerCard";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { buttonClass, cx } from "@/components/ui";

export const metadata: Metadata = { title: "Choose a practice broker", robots: { index: false, follow: false } };

const STARTING_BALANCE = "1000000";

async function selectBroker(formData: FormData) {
  "use server";
  const userId = await getSessionUserId();
  if (!userId) redirect("/sign-in");

  const brokerId = String(formData.get("brokerId") ?? "");
  const db = getDb();
  const [broker] = await db.select({ id: brokerCatalog.id }).from(brokerCatalog).where(eq(brokerCatalog.id, brokerId)).limit(1);
  if (!broker) redirect("/onboarding/broker");

  await ensureUserRow(userId);
  const [created] = await db
    .insert(virtualAccounts)
    .values({ userId, brokerId: broker.id, cashBalance: STARTING_BALANCE, startingBalance: STARTING_BALANCE })
    .onConflictDoNothing({ target: virtualAccounts.userId })
    .returning({ id: virtualAccounts.id });
  if (created) await track("onboarding_completed", { broker_id: broker.id, ...(await readCampaign()) }, created.id);

  redirect("/dashboard");
}

function sampleCost(b: BrokerRow): number {
  return roundTripCharges(SAMPLE_TURNOVER, deliveryFeesFromRow(b));
}

function BrokerOption({ broker }: { broker: BrokerRow }) {
  return (
    <label className="group block cursor-pointer rounded-xl border border-line bg-raised p-4 transition-colors hover:border-accent has-[:checked]:border-accent has-[:checked]:bg-accent-soft">
      <BrokerCard
        broker={broker}
        action={<input type="radio" name="brokerId" value={broker.id} required className="mt-1 h-4 w-4 accent-[var(--accent)]" />}
      />
    </label>
  );
}

export default async function BrokerOnboardingPage() {
  const userId = await getSessionUserId();
  if (!userId) redirect("/sign-in");

  const [existing] = await getDb().select().from(virtualAccounts).where(eq(virtualAccounts.userId, userId)).limit(1);
  if (existing) redirect("/dashboard");

  const brokers = await getAllBrokers();
  const byCost = (a: BrokerRow, b: BrokerRow) => sampleCost(a) - sampleCost(b) || a.brand.localeCompare(b.brand);
  const complete = brokers.filter((b) => b.feeScheduleComplete).sort(byCost);
  const indicative = brokers.filter((b) => !b.feeScheduleComplete).sort(byCost);

  return (
    <>
      <AppHeader signedIn showNav={false} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
        <p className="text-sm font-medium text-accent-ink">One step to start</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink">Choose a broker to practise with</h1>
        <p className="mt-2 max-w-2xl text-muted">
          Your virtual trades are costed with this broker&apos;s real, published fees, so you learn what investing
          actually costs. You start with ₹10,00,000 of virtual cash. You can switch broker any time, and no real account
          is opened by this step.
        </p>

        <form action={selectBroker} className="mt-8 flex flex-col gap-8">
          <section>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold text-ink">Brokers with a full fee schedule on file</h2>
              <span className="text-xs text-muted">Sorted by the all-in cost of a ₹1 lakh buy and sell</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {complete.map((b) => (
                <BrokerOption key={b.id} broker={b} />
              ))}
            </div>
          </section>

          {indicative.length > 0 && (
            <details className="group rounded-xl border border-line bg-sub p-4">
              <summary className="cursor-pointer select-none font-medium text-ink">
                {indicative.length} more brokers with indicative fees
                <span className="ml-2 text-sm font-normal text-muted">
                  (BrokerLens does not yet hold their full schedule, so costs here are approximate)
                </span>
              </summary>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {indicative.map((b) => (
                  <BrokerOption key={b.id} broker={b} />
                ))}
              </div>
            </details>
          )}

          <div className="sticky bottom-0 -mx-4 border-t border-line bg-bg/95 px-4 py-4 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
            <button type="submit" className={cx(buttonClass("primary"), "w-full py-3 text-base sm:w-auto")}>
              Start with ₹10,00,000 of virtual cash
            </button>
          </div>
        </form>
      </main>
      <SiteFooter />
    </>
  );
}

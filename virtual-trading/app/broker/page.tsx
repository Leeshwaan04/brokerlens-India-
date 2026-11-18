import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog, virtualAccounts } from "@/lib/schema";
import { BrokerCard } from "@/components/BrokerCard";

function inr(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

function feeLine(flat: number, pct: number): string {
  if (flat > 0 && pct > 0) return `Lower of ${inr(flat)} or ${(pct * 100).toFixed(2)}%`;
  if (pct > 0) return `${(pct * 100).toFixed(2)}% of order value`;
  if (flat > 0) return `${inr(flat)} flat`;
  return "No brokerage";
}

async function switchBroker(formData: FormData) {
  "use server";
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const brokerId = String(formData.get("brokerId") ?? "");
  if (!brokerId || brokerId === current.account.brokerId) return;

  const db = getDb();
  await db.update(virtualAccounts).set({ brokerId }).where(eq(virtualAccounts.id, current.account.id));
}

export default async function BrokerPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const db = getDb();
  const [currentBroker, allBrokers] = await Promise.all([
    db.select().from(brokerCatalog).where(eq(brokerCatalog.id, current.account.brokerId)).limit(1),
    db.select().from(brokerCatalog),
  ]);
  const broker = currentBroker[0];
  if (!broker) redirect("/onboarding/broker");

  const otherBrokers = allBrokers.filter((b) => b.id !== broker.id);

  return (
    <main className="mx-auto max-w-2xl flex-1 p-8">
      <h1 className="mb-6 text-2xl font-semibold">Your broker</h1>

      <div className="mb-6 rounded-lg border p-5">
        <BrokerCard broker={broker} />
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-gray-500">Delivery brokerage</dt>
          <dd>{feeLine(Number(broker.deliveryFlat), Number(broker.deliveryPct))}</dd>
          <dt className="text-gray-500">Intraday brokerage</dt>
          <dd>{feeLine(Number(broker.intradayFlat), Number(broker.intradayPct))}</dd>
          <dt className="text-gray-500">DP charge (per scrip, on sell)</dt>
          <dd>{inr(Number(broker.dpCharge))}</dd>
          {broker.dematAmc != null && (
            <>
              <dt className="text-gray-500">Demat AMC</dt>
              <dd>{inr(Number(broker.dematAmc))}</dd>
            </>
          )}
          {broker.accountOpen != null && (
            <>
              <dt className="text-gray-500">Account opening</dt>
              <dd>{inr(Number(broker.accountOpen))}</dd>
            </>
          )}
        </dl>
        <p className="mt-4 text-xs text-gray-500">
          These are the real, published figures used to cost your virtual trades here. They are not a quote
          or an offer; confirm current charges on the broker&apos;s own site before opening a real account.
        </p>
        <a
          href={broker.ctaUrl}
          target="_blank"
          rel="noopener noreferrer nofollow sponsored"
          className="mt-4 inline-block rounded-md bg-black px-5 py-2.5 text-white dark:bg-white dark:text-black"
        >
          Open a real account with {broker.brand}
        </a>
      </div>

      <h2 className="mb-3 text-lg font-medium">Switch broker</h2>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Switching only changes which broker&apos;s fee schedule costs your future virtual trades. It does not
        affect your cash balance, holdings, or order history.
      </p>
      <form action={switchBroker} className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {otherBrokers.map((b) => (
            <label
              key={b.id}
              className="cursor-pointer rounded-lg border p-4 hover:border-black dark:hover:border-white"
            >
              <BrokerCard
                broker={b}
                action={<input type="radio" name="brokerId" value={b.id} required className="h-4 w-4" />}
              />
            </label>
          ))}
        </div>
        <button
          type="submit"
          className="self-start rounded-md border px-5 py-2.5 disabled:opacity-50"
          disabled={otherBrokers.length === 0}
        >
          Switch
        </button>
      </form>
    </main>
  );
}

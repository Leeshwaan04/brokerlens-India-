import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db";
import { brokerCatalog, virtualAccounts } from "@/lib/schema";
import { BrokerCard } from "@/components/BrokerCard";

async function selectBroker(formData: FormData) {
  "use server";
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  const brokerId = String(formData.get("brokerId") ?? "");
  if (!brokerId) return;

  const db = getDb();
  await db
    .insert(virtualAccounts)
    .values({ userId, brokerId, cashBalance: "1000000", startingBalance: "1000000" })
    .onConflictDoNothing({ target: virtualAccounts.userId });

  redirect("/dashboard");
}

export default async function BrokerOnboardingPage() {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  const db = getDb();
  const [existing] = await db.select().from(virtualAccounts).where(eq(virtualAccounts.userId, userId)).limit(1);
  if (existing) redirect("/dashboard");

  const brokers = await db.select().from(brokerCatalog);

  return (
    <main className="mx-auto max-w-3xl flex-1 p-8">
      <h1 className="mb-2 text-2xl font-semibold">Choose a broker to practice with</h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
        This only decides which broker&apos;s real, published fee schedule is used to cost your virtual
        trades. You start with a virtual balance of Rs 10,00,000. No real account is opened by this step.
      </p>
      <form action={selectBroker} className="flex flex-col gap-6">
        <div className="grid gap-4 sm:grid-cols-2">
          {brokers.map((b) => (
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
          className="self-start rounded-md bg-black px-5 py-2.5 text-white dark:bg-white dark:text-black"
        >
          Continue
        </button>
      </form>
    </main>
  );
}

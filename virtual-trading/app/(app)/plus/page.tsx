import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { after } from "next/server";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { PLANS, plusActive, razorpayConfig, type PlanId } from "@/lib/billing";
import { getDb } from "@/lib/db";
import { track } from "@/lib/events";
import { users } from "@/lib/schema";
import { PlusCheckout } from "@/components/PlusCheckout";
import { buttonClass, Card, CardTitle, Notice, PageHeader, Pill } from "@/components/ui";

export const metadata: Metadata = { title: "BrokerLens Plus" };

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN")}`;

export default async function PlusPage({ searchParams }: { searchParams: Promise<{ from?: string }> }) {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  const [user] = await getDb().select({ plusUntil: users.plusUntil }).from(users).where(eq(users.id, current.userId)).limit(1);
  const active = plusActive(user?.plusUntil);
  const cfg = razorpayConfig();
  const { from } = await searchParams;
  const accountId = current.account.id;
  after(() => track("plus_viewed", { active, from: from === "statement" ? "statement" : "direct" }, accountId));

  return (
    <>
      <PageHeader
        title="BrokerLens Plus"
        subtitle="The practice market stays free for everyone. Plus adds tools for people who practise seriously."
        action={active ? <Pill tone="up">Plus active</Pill> : undefined}
      />

      {from === "statement" && !active && (
        <div className="mb-6">
          <Notice tone="info">Downloading your full statement is part of Plus.</Notice>
        </div>
      )}

      {active && user?.plusUntil && (
        <div className="mb-6">
          <Notice tone="up">
            Plus is active until{" "}
            {user.plusUntil.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Kolkata" })}. Buying
            again adds time from that date.{" "}
            <a href="/api/reports/statement" className="font-medium text-accent-ink underline-offset-2 hover:underline">
              Download your statement
            </a>
          </Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardTitle>What Plus includes</CardTitle>
          <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-muted">
            <li>
              <span className="text-ink">Your full practice statement.</span> Every order with its fill, each charge and tax
              (brokerage, STT, exchange and SEBI fees, stamp duty, GST, DP), and the cash it moved or its intraday P&amp;L, as a
              spreadsheet file, like the statement a broker gives you.
            </li>
            <li>
              <span className="text-ink">The same free practice market.</span> Nothing you can do today is taken away. Rankings
              of brokers stay ordered by cost alone, paid or not.
            </li>
          </ul>
          <p className="mt-4 text-xs text-faint">
            A one-time payment for a fixed period, with no automatic renewal. Payments are processed by Razorpay; your card,
            UPI or bank details go to Razorpay and never reach BrokerLens. Plus is for practice and learning, not investment
            advice.
          </p>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
          {(Object.keys(PLANS) as PlanId[]).map((id) => {
            const p = PLANS[id];
            return (
              <Card key={id}>
                <h2 className="font-semibold text-ink">{p.label}</h2>
                <div className="num mt-2 text-3xl font-semibold text-ink">{rupees(p.amountPaise)}</div>
                <p className="mt-1 text-xs text-muted">
                  {id === "plus_year" ? `About ${rupees(Math.round(p.amountPaise / 12 / 100) * 100)} a month` : "For 30 days"}
                </p>
                <div className="mt-4">
                  {cfg ? (
                    <PlusCheckout plan={id} label={p.label} testMode={cfg.mode === "test"} />
                  ) : (
                    <p className="text-sm text-muted">Payments are not available yet.</p>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      <p className="mt-6 text-sm text-muted">
        Questions about a payment? Email <span className="font-medium text-ink">letmeknow@brokerlens.in</span>.{" "}
        <Link href="/account" className={buttonClass("ghost", "sm")}>
          Back to account
        </Link>
      </p>
    </>
  );
}

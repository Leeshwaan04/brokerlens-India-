import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog, users } from "@/lib/schema";
import { inr } from "@/lib/format";
import { deleteAccountAction, resetPortfolioAction } from "../actions";
import { ConfirmForm } from "@/components/ConfirmForm";
import { Card, CardTitle, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Account" };

export default async function AccountPage() {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");
  const db = getDb();
  const [[user], [broker]] = await Promise.all([
    db.select().from(users).where(eq(users.id, current.userId)).limit(1),
    db.select({ brand: brokerCatalog.brand }).from(brokerCatalog).where(eq(brokerCatalog.id, current.account.brokerId)).limit(1),
  ]);
  const started = current.account.createdAt.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

  return (
    <>
      <PageHeader title="Account" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Your practice account</CardTitle>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-muted">Email</dt>
            <dd className="text-ink">{user?.email || "Not on file"}</dd>
            <dt className="text-muted">Practice broker</dt>
            <dd className="text-ink">
              {broker?.brand ?? current.account.brokerId}{" "}
              <Link href="/broker" className="text-accent-ink hover:underline">
                Change
              </Link>
            </dd>
            <dt className="text-muted">Starting cash</dt>
            <dd className="num text-ink">{inr(Number(current.account.startingBalance))}</dd>
            <dt className="text-muted">Portfolio started</dt>
            <dd className="text-ink">{started}</dd>
          </dl>
          <p className="mt-4 text-xs text-muted">
            What we store and why is in the{" "}
            <Link href="/privacy" className="text-accent-ink hover:underline">
              privacy notice
            </Link>
            .
          </p>
        </Card>

        <div className="flex flex-col gap-6">
          <Card>
            <CardTitle>Start over</CardTitle>
            <p className="mb-4 text-sm text-muted">
              Clears your holdings, orders and history and restores {inr(Number(current.account.startingBalance))} of virtual
              cash. Your practice broker and watchlist stay. This cannot be undone.
            </p>
            <ConfirmForm action={resetPortfolioAction} word="RESET" buttonLabel="Reset portfolio" />
          </Card>

          <Card className="border-down/30">
            <CardTitle>Delete account</CardTitle>
            <p className="mb-4 text-sm text-muted">
              Permanently deletes your sign-in, practice account and all its data. Account-opening clicks are kept only as
              anonymous counts. This cannot be undone.
            </p>
            <ConfirmForm action={deleteAccountAction} word="DELETE" buttonLabel="Delete my account" danger />
          </Card>
        </div>
      </div>
    </>
  );
}

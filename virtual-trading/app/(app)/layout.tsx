import type { ReactNode } from "react";
import { eq } from "drizzle-orm";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { brokerCatalog } from "@/lib/schema";

// Shell for every signed-in page. Each page still does its own auth and
// onboarding redirect: a layout is not re-rendered on client-side navigation
// between its pages, so it cannot be the only gate.
export default async function AppLayout({ children }: { children: ReactNode }) {
  const current = await getCurrentAccount();
  let brokerBrand: string | null = null;
  if (current?.account) {
    const [b] = await getDb()
      .select({ brand: brokerCatalog.brand })
      .from(brokerCatalog)
      .where(eq(brokerCatalog.id, current.account.brokerId))
      .limit(1);
    brokerBrand = b?.brand ?? null;
  }

  return (
    <>
      <AppHeader signedIn={current !== null} brokerBrand={brokerBrand} />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      <SiteFooter />
    </>
  );
}

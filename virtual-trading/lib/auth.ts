import { auth } from "@clerk/nextjs/server";
import { eq } from "drizzle-orm";
import { getDb } from "./db";
import { virtualAccounts } from "./schema";

export interface CurrentAccount {
  userId: string;
  account: typeof virtualAccounts.$inferSelect | null;
}

/**
 * The signed-in Clerk user id, and that user's virtual_accounts row if they
 * have completed broker onboarding. Call from a Server Component or Route
 * Handler; redirect to /sign-in (middleware already does this for protected
 * routes) or /onboarding/broker as appropriate when account is null.
 */
export async function getCurrentAccount(): Promise<CurrentAccount | null> {
  const { userId } = await auth();
  if (!userId) return null;

  const db = getDb();
  const [account] = await db.select().from(virtualAccounts).where(eq(virtualAccounts.userId, userId)).limit(1);

  return { userId, account: account ?? null };
}

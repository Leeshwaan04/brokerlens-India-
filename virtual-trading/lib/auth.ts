import { currentUser } from "@clerk/nextjs/server";
import { eq } from "drizzle-orm";
import { getDb } from "./db";
import { users, virtualAccounts } from "./schema";
import { devAuthUserId, getSessionUserId } from "./session";

export interface CurrentAccount {
  userId: string;
  account: typeof virtualAccounts.$inferSelect | null;
}

/**
 * The signed-in user id, and that user's virtual_accounts row if they have
 * completed broker onboarding. Call from a Server Component, Server Action or
 * Route Handler; redirect to /sign-in or /onboarding/broker as appropriate.
 */
export async function getCurrentAccount(): Promise<CurrentAccount | null> {
  const userId = await getSessionUserId();
  if (!userId) return null;

  const db = getDb();
  const [account] = await db.select().from(virtualAccounts).where(eq(virtualAccounts.userId, userId)).limit(1);

  return { userId, account: account ?? null };
}

/**
 * Makes sure this user has a users row before anything references it.
 * virtual_accounts.user_id is a foreign key to users.id, and that row was
 * only ever written by Clerk's user.created webhook, so a sign-up that
 * reached onboarding before the webhook arrived (or with no webhook
 * configured at all) failed with a foreign-key error instead of an account.
 */
export async function ensureUserRow(userId: string): Promise<void> {
  const db = getDb();
  const [existing] = await db.select({ id: users.id }).from(users).where(eq(users.id, userId)).limit(1);
  if (existing) return;

  let email = "";
  let displayName: string | null = null;
  if (devAuthUserId()) {
    email = "dev@localhost";
    displayName = "Local developer";
  } else {
    const u = await currentUser();
    email = u?.primaryEmailAddress?.emailAddress ?? u?.emailAddresses?.[0]?.emailAddress ?? "";
    displayName = [u?.firstName, u?.lastName].filter(Boolean).join(" ") || null;
  }
  await db.insert(users).values({ id: userId, email, displayName }).onConflictDoNothing({ target: users.id });
}

// Starting over, and deleting everything a user has, in one transaction each.

import { eq, inArray } from "drizzle-orm";
import { getDb } from "./db";
import {
  ctaClicks,
  holdings,
  orders,
  performanceSnapshots,
  realizedPnlEvents,
  users,
  virtualAccounts,
  watchlistItems,
} from "./schema";

/**
 * Clears an account's portfolio and trade history and restores its starting
 * cash, keeping the account, its practice broker and its watchlist. Rows are
 * deleted children first because the foreign keys do not cascade.
 */
export async function resetPortfolio(accountId: string): Promise<void> {
  await getDb().transaction(async (tx) => {
    const [account] = await tx.select().from(virtualAccounts).where(eq(virtualAccounts.id, accountId)).for("update");
    if (!account) return;
    await tx.delete(realizedPnlEvents).where(eq(realizedPnlEvents.accountId, accountId));
    await tx.delete(performanceSnapshots).where(eq(performanceSnapshots.accountId, accountId));
    await tx.delete(holdings).where(eq(holdings.accountId, accountId));
    await tx.delete(orders).where(eq(orders.accountId, accountId));
    await tx
      .update(virtualAccounts)
      .set({ cashBalance: account.startingBalance, createdAt: new Date() })
      .where(eq(virtualAccounts.id, accountId));
  });
}

/**
 * Deletes a user and every row tied to them, as the privacy notice promises.
 * Account-opening clicks are kept as anonymous counts: the link to the
 * account is removed, so nothing left identifies the person.
 */
export async function deleteUserData(userId: string): Promise<boolean> {
  return getDb().transaction(async (tx) => {
    const accounts = await tx.select({ id: virtualAccounts.id }).from(virtualAccounts).where(eq(virtualAccounts.userId, userId));
    const ids = accounts.map((a) => a.id);
    if (ids.length) {
      await tx.update(ctaClicks).set({ accountId: null }).where(inArray(ctaClicks.accountId, ids));
      await tx.delete(watchlistItems).where(inArray(watchlistItems.accountId, ids));
      await tx.delete(realizedPnlEvents).where(inArray(realizedPnlEvents.accountId, ids));
      await tx.delete(performanceSnapshots).where(inArray(performanceSnapshots.accountId, ids));
      await tx.delete(holdings).where(inArray(holdings.accountId, ids));
      await tx.delete(orders).where(inArray(orders.accountId, ids));
      await tx.delete(virtualAccounts).where(inArray(virtualAccounts.id, ids));
    }
    const deleted = await tx.delete(users).where(eq(users.id, userId)).returning({ id: users.id });
    return deleted.length > 0 || ids.length > 0;
  });
}

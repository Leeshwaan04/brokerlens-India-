// One performance_snapshots row per account per ingested trading day, written
// by the EOD cron after settlement. This is what the performance page's
// portfolio-value chart plots; the table existed from Slice 1 but nothing
// ever wrote to it.

import { asc, eq } from "drizzle-orm";
import { getDb } from "./db";
import { performanceSnapshots, virtualAccounts } from "./schema";
import { getAccountSummary } from "./account-summary";

export async function writeSnapshotsFor(tradeDate: string): Promise<number> {
  const db = getDb();
  const accounts = await db.select().from(virtualAccounts);
  let written = 0;
  for (const account of accounts) {
    const s = await getAccountSummary(account, tradeDate);
    if (!s) continue;
    const values = {
      accountId: account.id,
      snapshotDate: tradeDate,
      portfolioValue: String(s.portfolioValue),
      cashBalance: String(s.cash),
      holdingsValue: String(s.holdingsValue),
      unrealizedPnl: String(s.unrealizedPnl),
      realizedPnlCumulative: String(s.realizedPnl),
      totalReturnPct: String(s.totalReturnPct),
      numClosedTrades: s.closedTrades,
      winRate: s.winRate === null ? null : String(s.winRate),
      confidenceScore: s.score.enoughTrades ? String(s.score.score) : null,
    };
    await db
      .insert(performanceSnapshots)
      .values(values)
      .onConflictDoUpdate({ target: [performanceSnapshots.accountId, performanceSnapshots.snapshotDate], set: values });
    written++;
  }
  return written;
}

export async function getSnapshots(accountId: string) {
  return getDb()
    .select({ snapshotDate: performanceSnapshots.snapshotDate, portfolioValue: performanceSnapshots.portfolioValue })
    .from(performanceSnapshots)
    .where(eq(performanceSnapshots.accountId, accountId))
    .orderBy(asc(performanceSnapshots.snapshotDate));
}

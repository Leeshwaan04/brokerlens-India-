// Splits, bonuses and consolidations, detected from NSE's own bhavcopy.
//
// On an ex-date NSE prints the previous close (PrvsClsgPric) already
// adjusted for the action: after a 1:5 split, a ₹1,000 close is printed as
// ₹200. Comparing that with the close actually stored for the immediately
// previous session therefore gives the share-count factor exactly. On every
// other day the two are equal (a normal price move changes today's close,
// not yesterday's), so nothing fires. Without this, a split would show as an
// 80% loss and a bonus as a 50% loss.
//
// Dividends are deliberately not credited: real brokers pay them to the
// investor's bank account, not into the trading balance, and their holdings
// screens show the ex-dividend price drop the same way.

import { and, desc, eq, gte, lt } from "drizzle-orm";
import { getDb } from "./db";
import { corporateActionEvents, dailyPrices, holdings, orders } from "./schema";

export interface ShareAdjustment {
  factor: number; // new shares per old share
  ratio: string; // "new:old", e.g. "5:1"
}

// Above rounding noise on the printed price, below any real share action.
const MIN_CHANGE = 0.02;
// How close the observed ratio must be to a simple new:old ratio.
const RATIO_TOLERANCE = 0.01;
const MAX_DENOMINATOR = 10;
// A real split, bonus or consolidation moves the share count by at least a fifth (a 1:5 bonus is
// 6:5). Smaller printed differences (7:6, 10:9, 11:10) are what an unseen weekend special session
// (Budget Saturday, Muhurat) or any ordinary price gap produces, and they would match a "ratio" by
// chance. They are reported as unrecognised, never applied: a wrong adjustment silently changes
// holdings, a missed one is flagged to the owner. A genuine 1:10 bonus is the cost of that rule.
const MIN_FACTOR = 1.18;

/**
 * The share-count factor implied by NSE's printed previous close, or null
 * when there is none, or when the adjustment is not a recognisable share
 * ratio (a rights issue or an extraordinary dividend, which are logged by
 * the caller rather than guessed at).
 */
export function detectShareAdjustment(storedPrevClose: number, nsePrevClose: number | null): ShareAdjustment | null {
  if (!nsePrevClose || nsePrevClose <= 0 || storedPrevClose <= 0) return null;
  const raw = storedPrevClose / nsePrevClose;
  if (Math.abs(raw - 1) < MIN_CHANGE) return null;
  for (let old = 1; old <= MAX_DENOMINATOR; old++) {
    const neu = Math.round(raw * old);
    if (neu < 1 || neu === old) continue;
    const factor = neu / old;
    if (Math.abs(factor - raw) / raw > RATIO_TOLERANCE) continue;
    if (factor < MIN_FACTOR && factor > 1 / MIN_FACTOR) return null;
    return { factor, ratio: `${neu}:${old}` };
  }
  return null;
}

/** New quantity and per-share cost after an adjustment, keeping total cost basis unchanged. */
export function adjustHolding(qty: number, avgCost: number, factor: number): { qty: number; avgCost: number } {
  const newQty = Math.floor(qty * factor);
  if (newQty < 1) return { qty: 0, avgCost: 0 };
  return { qty: newQty, avgCost: (avgCost * qty) / newQty };
}

export interface AppliedAction {
  symbol: string;
  exDate: string;
  ratio: string;
  holdingsAdjusted: number;
  ordersCancelled: number;
}

export interface UnrecognisedAdjustment {
  symbol: string;
  exDate: string;
  storedPrevClose: number;
  nsePrevClose: number;
}

/**
 * Detects and applies every share action whose ex-date is `day`. Idempotent:
 * an action already recorded in corporate_action_events is never applied
 * twice. Pending orders in the stock targeting the ex-date or later are
 * cancelled, as brokers cancel open orders on an ex-date, because their
 * quantity and price were set before the share count changed.
 */
export async function applyCorporateActionsFor(
  day: string,
): Promise<{ applied: AppliedAction[]; unrecognised: UnrecognisedAdjustment[] }> {
  const db = getDb();
  const applied: AppliedAction[] = [];
  const unrecognised: UnrecognisedAdjustment[] = [];

  const [prevSession] = await db
    .selectDistinct({ tradeDate: dailyPrices.tradeDate })
    .from(dailyPrices)
    .where(lt(dailyPrices.tradeDate, day))
    .orderBy(desc(dailyPrices.tradeDate))
    .limit(1);
  if (!prevSession) return { applied, unrecognised };

  const [today, previous] = await Promise.all([
    db.select({ symbol: dailyPrices.symbol, prevClose: dailyPrices.prevClose }).from(dailyPrices).where(eq(dailyPrices.tradeDate, day)),
    db.select({ symbol: dailyPrices.symbol, close: dailyPrices.close }).from(dailyPrices).where(eq(dailyPrices.tradeDate, prevSession.tradeDate)),
  ]);
  // Only the immediately previous session we hold: with a gap in the data, a
  // genuine price move could otherwise look like a ratio.
  const prevClose = new Map(previous.map((r) => [r.symbol, Number(r.close)]));

  for (const row of today) {
    const stored = prevClose.get(row.symbol);
    if (stored === undefined || row.prevClose === null) continue;
    const nse = Number(row.prevClose);
    const adj = detectShareAdjustment(stored, nse);
    if (!adj) {
      if (Math.abs(stored / nse - 1) >= MIN_CHANGE) unrecognised.push({ symbol: row.symbol, exDate: day, storedPrevClose: stored, nsePrevClose: nse });
      continue;
    }
    const result = await applyShareAdjustment(row.symbol, day, adj);
    if (result) applied.push(result);
  }
  return { applied, unrecognised };
}

async function applyShareAdjustment(symbol: string, exDate: string, adj: ShareAdjustment): Promise<AppliedAction | null> {
  return getDb().transaction(async (tx) => {
    const [event] = await tx
      .insert(corporateActionEvents)
      .values({ symbol, exDate, factor: String(adj.factor), ratio: adj.ratio, holdingsAdjusted: 0, ordersCancelled: 0 })
      .onConflictDoNothing()
      .returning({ id: corporateActionEvents.id });
    if (!event) return null; // already applied by an earlier run

    const held = await tx.select().from(holdings).where(eq(holdings.symbol, symbol)).for("update");
    for (const h of held) {
      const next = adjustHolding(h.qty, Number(h.avgCost), adj.factor);
      if (next.qty === 0) {
        await tx.delete(holdings).where(eq(holdings.id, h.id));
      } else {
        await tx.update(holdings).set({ qty: next.qty, avgCost: String(next.avgCost) }).where(eq(holdings.id, h.id));
      }
    }

    const cancelled = await tx
      .update(orders)
      .set({ status: "CANCELLED", rejectionReason: "corporate_action" })
      .where(and(eq(orders.symbol, symbol), eq(orders.status, "PENDING"), gte(orders.targetTradeDate, exDate)))
      .returning({ id: orders.id });

    await tx
      .update(corporateActionEvents)
      .set({ holdingsAdjusted: held.length, ordersCancelled: cancelled.length })
      .where(eq(corporateActionEvents.id, event.id));

    return { symbol, exDate, ratio: adj.ratio, holdingsAdjusted: held.length, ordersCancelled: cancelled.length };
  });
}

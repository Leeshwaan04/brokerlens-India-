import { asc, eq } from "drizzle-orm";
import { getDb } from "./db";
import { brokerCatalog, CTA_PLACEMENTS, type CtaPlacement } from "./schema";
import { deliveryFeesFromRow } from "./trade-costs";
import type { ReplayBroker } from "./cost-replay";

export type BrokerRow = typeof brokerCatalog.$inferSelect;

export async function getAllBrokers(): Promise<BrokerRow[]> {
  return getDb().select().from(brokerCatalog).orderBy(asc(brokerCatalog.brand));
}

/**
 * Brokers whose full fee schedule brokerlens.in has on file. Every cost
 * ranking in the app is limited to these, so no broker is ranked cheaper or
 * dearer on an incomplete or indicative schedule.
 */
export async function getRankableBrokers(): Promise<BrokerRow[]> {
  return getDb().select().from(brokerCatalog).where(eq(brokerCatalog.feeScheduleComplete, true));
}

export function toReplayBroker(row: BrokerRow): ReplayBroker {
  return { id: row.id, brand: row.brand, fees: deliveryFeesFromRow(row) };
}

/** Tracked outbound link to a broker's real account-opening page. */
export function goHref(brokerId: string, placement: CtaPlacement): string {
  return `/go/${encodeURIComponent(brokerId)}?src=${placement}`;
}

export function parsePlacement(value: string | null): CtaPlacement {
  return (CTA_PLACEMENTS as readonly string[]).includes(value ?? "") ? (value as CtaPlacement) : "other";
}

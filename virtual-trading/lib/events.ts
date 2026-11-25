// Server-side product analytics. See the events table in schema.ts for what
// may and may not be stored.

import { cookies } from "next/headers";
import { eq, and, or, isNull, lt } from "drizzle-orm";
import { getDb } from "./db";
import { events, virtualAccounts, type EventName } from "./schema";
import { istDate } from "./market-calendar";

type Props = Record<string, string | number | boolean | null>;

/** Records one event. Never throws: analytics must not break a user action. */
export async function track(name: EventName, props: Props = {}, accountId: string | null = null): Promise<void> {
  try {
    await getDb().insert(events).values({ name, props, accountId });
  } catch (err) {
    console.error("event tracking failed", name, err);
  }
}

/** An order value as a coarse bucket, never the exact amount. */
export function valueBucket(rupees: number): string {
  if (rupees < 10_000) return "under_10k";
  if (rupees < 50_000) return "10k_50k";
  if (rupees < 1_00_000) return "50k_1l";
  if (rupees < 5_00_000) return "1l_5l";
  return "5l_plus";
}

// Set by proxy.ts when a visitor arrives with utm_* tags, so the campaign
// survives the trip through sign-up. Holds only the tags, no identifier.
export const CAMPAIGN_COOKIE = "vt_src";
const TAG = /^[a-z0-9_.-]{1,40}$/i;

export function encodeCampaign(params: URLSearchParams): string | null {
  const parts = ["utm_source", "utm_medium", "utm_campaign"].map((k) => params.get(k) ?? "");
  if (!parts[0] || !parts.every((p) => p === "" || TAG.test(p))) return null;
  return parts.join("|");
}

export async function readCampaign(): Promise<Props> {
  try {
    const raw = (await cookies()).get(CAMPAIGN_COOKIE)?.value ?? "";
    const [source, medium, campaign] = raw.split("|");
    if (!source || !TAG.test(source)) return {};
    return {
      utm_source: source,
      utm_medium: medium && TAG.test(medium) ? medium : null,
      utm_campaign: campaign && TAG.test(campaign) ? campaign : null,
    };
  } catch {
    return {};
  }
}

/** Marks the account active today (India time), writing at most once per account per day. */
export async function touchLastActive(accountId: string): Promise<void> {
  const today = istDate();
  try {
    await getDb()
      .update(virtualAccounts)
      .set({ lastActiveOn: today })
      .where(and(eq(virtualAccounts.id, accountId), or(isNull(virtualAccounts.lastActiveOn), lt(virtualAccounts.lastActiveOn, today))));
  } catch (err) {
    console.error("last-active update failed", err);
  }
}

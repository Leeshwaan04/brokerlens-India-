// Public health check for the uptime workflow
// (.github/workflows/virtual-trading-uptime.yml): 200 when the database
// answers, 503 when it does not, plus how many days of stored closes remain
// before the practice market runs out (lib/health.ts). Reveals nothing beyond
// the date of the newest NSE close, which every page shows anyway.
import { NextResponse } from "next/server";
import { max } from "drizzle-orm";
import { getDb } from "@/lib/db";
import { dailyPrices } from "@/lib/schema";
import { istDate } from "@/lib/market-calendar";
import { priceLagDays } from "@/lib/market-clock";
import { priceRunwayDays, priceSupplyStatus } from "@/lib/health";

export const dynamic = "force-dynamic";

const NO_STORE = { "cache-control": "no-store" };

export async function GET() {
  try {
    const [row] = await getDb().select({ latest: max(dailyPrices.tradeDate) }).from(dailyPrices);
    const latestClose = row?.latest ?? null;
    const runway = latestClose ? priceRunwayDays(latestClose, istDate(), priceLagDays()) : null;
    return NextResponse.json(
      { ok: true, db: "ok", latestClose, priceRunwayDays: runway, prices: priceSupplyStatus(runway) },
      { headers: NO_STORE },
    );
  } catch (err) {
    console.error("health check: database did not answer:", err instanceof Error ? err.message : err);
    return NextResponse.json({ ok: false, db: "error" }, { status: 503, headers: NO_STORE });
  }
}

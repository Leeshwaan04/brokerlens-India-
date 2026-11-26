import { NextRequest, NextResponse } from "next/server";
import { and, asc, eq, ilike, or } from "drizzle-orm";
import { getSessionUserId } from "@/lib/session";
import { getDb } from "@/lib/db";
import { stockUniverse } from "@/lib/schema";

export async function GET(request: NextRequest) {
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Strip control characters (a NUL makes Postgres error) and escape LIKE's
  // own wildcards so they match literally.
  const q = (request.nextUrl.searchParams.get("q") ?? "")
    .replace(/[\u0000-\u001f]/g, "")
    .trim()
    .slice(0, 40)
    .replace(/[\\%_]/g, (c) => `\\${c}`);
  if (q.length < 1) return NextResponse.json({ results: [] });

  const db = getDb();
  const results = await db
    .select({ symbol: stockUniverse.symbol, name: stockUniverse.name })
    .from(stockUniverse)
    .where(
      and(
        eq(stockUniverse.isActive, true),
        or(ilike(stockUniverse.symbol, `%${q}%`), ilike(stockUniverse.name, `%${q}%`)),
      ),
    )
    .orderBy(asc(stockUniverse.symbol))
    .limit(12);

  return NextResponse.json({ results });
}

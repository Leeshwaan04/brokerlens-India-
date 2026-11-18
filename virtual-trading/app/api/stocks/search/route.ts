import { NextRequest, NextResponse } from "next/server";
import { ilike, or } from "drizzle-orm";
import { auth } from "@clerk/nextjs/server";
import { getDb } from "@/lib/db";
import { stockUniverse } from "@/lib/schema";

export async function GET(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (q.length < 1) return NextResponse.json({ results: [] });

  const db = getDb();
  const results = await db
    .select()
    .from(stockUniverse)
    .where(or(ilike(stockUniverse.symbol, `%${q}%`), ilike(stockUniverse.name, `%${q}%`)))
    .limit(20);

  return NextResponse.json({ results });
}

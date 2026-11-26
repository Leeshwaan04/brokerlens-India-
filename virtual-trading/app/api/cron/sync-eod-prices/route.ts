// Bearer-guarded trigger for the daily EOD price sync (lib/eod-sync.ts).
// In production the sync runs as a Node script in GitHub Actions
// (scripts/eod-sync.mts) because it needs more CPU than a Workers Free plan
// request allows; this route is for hosts without that limit, and for a
// manual backfill with ?date=YYYY-MM-DD and ?history=N.
import { NextRequest, NextResponse } from "next/server";
import { safeEqual } from "@/lib/billing";
import { runEodSync } from "@/lib/eod-sync";

export async function GET(request: NextRequest) {
  const cronSecret = process.env.CRON_SECRET;
  const authHeader = request.headers.get("authorization");
  if (!cronSecret || !safeEqual(authHeader ?? "", `Bearer ${cronSecret}`)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const params = request.nextUrl.searchParams;
  const date = params.get("date");
  if (date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return NextResponse.json({ error: "date must be YYYY-MM-DD" }, { status: 400 });
  }
  const { status, body } = await runEodSync({
    date: date ?? undefined,
    history: params.has("history") ? Number(params.get("history")) : undefined,
  });
  return NextResponse.json(body, { status });
}

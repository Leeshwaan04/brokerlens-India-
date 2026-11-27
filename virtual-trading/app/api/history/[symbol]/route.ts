// Adjusted daily history for the charting studio, capped at the practice
// market's date. Signed-in users only (the chart lives on a private page);
// the data itself is public NSE closes at least 30 days old.
import { NextResponse } from "next/server";
import { getSessionUserId } from "@/lib/session";
import { getHistory, SYMBOL_PATTERN } from "@/lib/history/query";

export async function GET(_request: Request, context: { params: Promise<{ symbol: string }> }) {
  if (!(await getSessionUserId())) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { symbol: raw } = await context.params;
  const symbol = decodeURIComponent(raw).toUpperCase();
  if (!SYMBOL_PATTERN.test(symbol)) return NextResponse.json({ error: "Unknown symbol" }, { status: 404 });
  const history = await getHistory(symbol);
  if (!history) return NextResponse.json({ error: "No history for this symbol yet" }, { status: 404 });
  return NextResponse.json(history, { headers: { "Cache-Control": "private, max-age=300" } });
}

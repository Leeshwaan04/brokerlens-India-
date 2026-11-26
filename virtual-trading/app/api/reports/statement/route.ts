import { NextResponse } from "next/server";
import { desc, eq } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { plusActive } from "@/lib/billing";
import { getDb } from "@/lib/db";
import { orders, users } from "@/lib/schema";

const COLUMNS = [
  "session_date", "symbol", "product", "side", "order_type", "validity", "qty", "status", "fill_price", "exit_price",
  "exit_reason", "turnover", "brokerage", "stt", "exchange_charges", "sebi_charges", "stamp_duty", "gst", "dp_charge",
  "total_charges", "cash_in_out_or_intraday_pnl", "note",
] as const;

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  // Quote everything that could break a row or be read as a formula.
  return /[",\n\r]|^[=+\-@]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

// Plus: every order with its fill, each charge and tax, and the cash it moved
// (or, for intraday, its P&L after charges), like a broker's statement.
export async function GET() {
  const current = await getCurrentAccount();
  if (!current?.account) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  const db = getDb();
  const [user] = await db.select({ plusUntil: users.plusUntil }).from(users).where(eq(users.id, current.userId)).limit(1);
  if (!plusActive(user?.plusUntil)) {
    return NextResponse.redirect(new URL("/plus?from=statement", process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3100"));
  }

  const rows = await db.select().from(orders).where(eq(orders.accountId, current.account.id)).orderBy(desc(orders.targetTradeDate));
  const lines = [COLUMNS.join(",")];
  for (const o of rows) {
    const cash = o.netAmount === null ? "" : o.product === "MIS" ? o.netAmount : (o.side === "BUY" ? "-" : "") + o.netAmount;
    lines.push(
      [
        o.targetTradeDate, o.symbol, o.product, o.side, o.orderType, o.validity, o.qty, o.status, o.fillPrice, o.exitPrice,
        o.exitReason, o.grossAmount, o.brokerage, o.stt, o.exchangeCharges, o.sebiCharges, o.stampDuty, o.gst, o.dpCharge,
        o.totalCharges, cash, o.rejectionReason ?? "",
      ]
        .map(csvCell)
        .join(","),
    );
  }
  const today = new Date().toISOString().slice(0, 10);
  return new NextResponse(`${lines.join("\r\n")}\r\n`, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="brokerlens-practice-statement-${today}.csv"`,
      "Cache-Control": "private, no-store",
    },
  });
}

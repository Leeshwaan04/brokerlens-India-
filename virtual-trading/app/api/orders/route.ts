import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { placeOrder, OrderPlacementError } from "@/lib/order-engine";
import type { OrderSide } from "@/lib/schema";

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json().catch(() => null);
  const symbol = typeof body?.symbol === "string" ? body.symbol.toUpperCase() : "";
  const side = body?.side as OrderSide;
  const qty = Number(body?.qty);

  if (!symbol || (side !== "BUY" && side !== "SELL") || !Number.isFinite(qty)) {
    return NextResponse.json({ error: "symbol, side ('BUY'|'SELL') and qty are required" }, { status: 400 });
  }

  try {
    const result = await placeOrder({ userId, symbol, side, qty });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof OrderPlacementError) {
      return NextResponse.json({ error: err.message }, { status: 422 });
    }
    console.error("placeOrder failed", err);
    return NextResponse.json({ error: "Could not place order" }, { status: 500 });
  }
}

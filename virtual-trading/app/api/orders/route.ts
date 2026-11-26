import { NextResponse } from "next/server";
import { crossSiteRejection } from "@/lib/request-guard";
import { getSessionUserId } from "@/lib/session";
import { placeOrder, OrderPlacementError } from "@/lib/order-engine";
import type { OrderType, Validity } from "@/lib/fills";
import type { OrderSide } from "@/lib/schema";

export async function POST(request: Request) {
  const refused = crossSiteRejection(request);
  if (refused) return refused;
  const userId = await getSessionUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json().catch(() => null);
  const symbol = typeof body?.symbol === "string" ? body.symbol.toUpperCase() : "";
  const side = body?.side as OrderSide;
  const qty = Number(body?.qty);
  const clientOrderId = typeof body?.clientOrderId === "string" ? body.clientOrderId : undefined;
  const orderType = typeof body?.orderType === "string" ? (body.orderType as OrderType) : undefined;
  const validity = typeof body?.validity === "string" ? (body.validity as Validity) : undefined;
  const limitPrice = typeof body?.limitPrice === "number" ? body.limitPrice : null;
  const triggerPrice = typeof body?.triggerPrice === "number" ? body.triggerPrice : null;
  const product = body?.product === "MIS" ? "MIS" : "CNC";
  const stopLossPrice = typeof body?.stopLossPrice === "number" ? body.stopLossPrice : null;
  const targetPrice = typeof body?.targetPrice === "number" ? body.targetPrice : null;

  if (!symbol || (side !== "BUY" && side !== "SELL") || !Number.isFinite(qty)) {
    return NextResponse.json({ error: "symbol, side ('BUY'|'SELL') and qty are required" }, { status: 400 });
  }

  try {
    const result = await placeOrder({ userId, symbol, side, qty, clientOrderId, orderType, validity, limitPrice, triggerPrice, product, stopLossPrice, targetPrice });
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof OrderPlacementError) {
      return NextResponse.json({ error: err.message }, { status: 422 });
    }
    console.error("placeOrder failed", err);
    return NextResponse.json({ error: "Could not place order" }, { status: 500 });
  }
}

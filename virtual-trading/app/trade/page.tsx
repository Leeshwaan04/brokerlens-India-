import { redirect } from "next/navigation";
import { eq, desc } from "drizzle-orm";
import { getCurrentAccount } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { stockUniverse, dailyPrices } from "@/lib/schema";
import { placeOrder, OrderPlacementError } from "@/lib/order-engine";
import { StockSearch } from "@/components/StockSearch";
import type { OrderSide } from "@/lib/schema";

async function placeOrderAction(formData: FormData) {
  "use server";
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");

  const symbol = String(formData.get("symbol") ?? "").toUpperCase();
  const side = formData.get("side") as OrderSide;
  const qty = Number(formData.get("qty"));

  let message: string;
  try {
    const result = await placeOrder({ userId: current.userId, symbol, side, qty });
    message = `ok:Order placed. It will fill at the ${result.targetTradeDate} close once published.`;
  } catch (err) {
    message = `error:${err instanceof OrderPlacementError ? err.message : "Could not place order."}`;
  }

  redirect(`/trade?symbol=${symbol}&result=${encodeURIComponent(message)}`);
}

export default async function TradePage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; result?: string }>;
}) {
  const current = await getCurrentAccount();
  if (!current) redirect("/sign-in");
  if (!current.account) redirect("/onboarding/broker");

  const { symbol, result } = await searchParams;
  const splitAt = result ? result.indexOf(":") : -1;
  const status = splitAt >= 0 ? result!.slice(0, splitAt) : undefined;
  const message = splitAt >= 0 ? result!.slice(splitAt + 1) : undefined;

  const db = getDb();
  let stock: typeof stockUniverse.$inferSelect | undefined;
  let lastClose: { close: string; tradeDate: string } | undefined;

  if (symbol) {
    [stock] = await db
      .select()
      .from(stockUniverse)
      .where(eq(stockUniverse.symbol, symbol.toUpperCase()))
      .limit(1);
    if (stock) {
      [lastClose] = await db
        .select({ close: dailyPrices.close, tradeDate: dailyPrices.tradeDate })
        .from(dailyPrices)
        .where(eq(dailyPrices.symbol, stock.symbol))
        .orderBy(desc(dailyPrices.tradeDate))
        .limit(1);
    }
  }

  return (
    <main className="mx-auto max-w-2xl flex-1 p-8">
      <h1 className="mb-6 text-2xl font-semibold">Place an order</h1>
      <StockSearch />

      {message && (
        <p className={`mt-4 rounded-md border p-3 text-sm ${status === "ok" ? "border-green-300 text-green-700" : "border-red-300 text-red-700"}`}>
          {message}
        </p>
      )}

      {symbol && !stock && <p className="mt-6 text-sm text-gray-600">No stock found for &quot;{symbol}&quot;.</p>}

      {stock && (
        <div className="mt-6 rounded-lg border p-5">
          <div className="mb-4">
            <div className="text-lg font-medium">
              {stock.symbol} &middot; {stock.name}
            </div>
            {lastClose ? (
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Last available close: Rs {Number(lastClose.close).toFixed(2)} ({lastClose.tradeDate})
              </div>
            ) : (
              <div className="text-sm text-amber-600">No price on file for this symbol yet.</div>
            )}
          </div>

          <form action={placeOrderAction} className="flex flex-col gap-3">
            <input type="hidden" name="symbol" value={stock.symbol} />
            <div className="flex gap-4">
              <label className="flex items-center gap-2">
                <input type="radio" name="side" value="BUY" defaultChecked /> Buy
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="side" value="SELL" /> Sell
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-sm text-gray-600 dark:text-gray-400">Quantity</span>
              <input type="number" name="qty" min={1} step={1} required className="w-32 rounded-md border px-3 py-2" />
            </label>
            <button
              type="submit"
              disabled={!lastClose}
              className="mt-2 self-start rounded-md bg-black px-5 py-2.5 text-white disabled:opacity-50 dark:bg-white dark:text-black"
            >
              Place order
            </button>
          </form>

          <p className="mt-4 text-xs text-gray-500">
            This order fills at the next official NSE close, not the price shown above, consistent with
            SEBI&apos;s restrictions on real-time data for investor-education platforms. It is never sent to
            a real exchange.
          </p>
        </div>
      )}
    </main>
  );
}

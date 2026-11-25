"use client";

import { useActionState, useMemo, useState } from "react";
import Link from "next/link";
import { placeOrderAction, type OrderActionState } from "@/app/(app)/actions";
import {
  buyLegFor,
  estimateBuyCost,
  maxAffordableQty,
  PRICE_MOVE_BUFFER_PCT,
  sellLegFor,
  type DeliveryFees,
  type LegCharges,
} from "@/lib/trade-costs";
import { inr, inrWhole, shortDate, signedInr, pnlTone } from "@/lib/format";
import { buttonClass, cx, Notice } from "./ui";

export interface TicketBroker {
  id: string;
  brand: string;
  fees: DeliveryFees;
}

interface Props {
  symbol: string;
  name: string;
  lastClose: number;
  lastCloseDate: string;
  defaultSide: "BUY" | "SELL";
  currentBroker: TicketBroker;
  rankable: TicketBroker[];
  freeCash: number;
  freeShares: number;
  avgCost: number | null;
  targetTradeDate: string;
  // Idempotency key generated on the server for this render.
  clientOrderId: string;
}

const INITIAL: OrderActionState = { status: "idle", message: "" };
const BUY_SIZES = [10_000, 25_000, 50_000, 1_00_000];

function legFor(side: "BUY" | "SELL", price: number, qty: number, fees: DeliveryFees): LegCharges {
  return side === "BUY" ? buyLegFor(price, qty, fees) : sellLegFor(price, qty, fees);
}

export function OrderTicket(props: Props) {
  const { symbol, lastClose, currentBroker, rankable, freeCash, freeShares, avgCost } = props;
  const [side, setSide] = useState<"BUY" | "SELL">(props.defaultSide === "SELL" && freeShares > 0 ? "SELL" : "BUY");
  const [qtyText, setQtyText] = useState("");
  const [clientOrderId, setClientOrderId] = useState(props.clientOrderId);
  const [state, formAction, pending] = useActionState(async (prev: OrderActionState, fd: FormData) => {
    const next = await placeOrderAction(prev, fd);
    if (next.status === "ok") {
      setQtyText("");
      // A new key for the next order; repeats of this one stay deduplicated.
      setClientOrderId(crypto.randomUUID());
    }
    return next;
  }, INITIAL);

  const qty = /^\d+$/.test(qtyText) ? Number(qtyText) : 0;
  const maxBuy = useMemo(() => maxAffordableQty(lastClose, freeCash, currentBroker.fees), [lastClose, freeCash, currentBroker.fees]);
  const leg = qty > 0 ? legFor(side, lastClose, qty, currentBroker.fees) : null;
  const reserve = side === "BUY" && qty > 0 ? estimateBuyCost(lastClose, qty, currentBroker.fees) : 0;

  const overCash = side === "BUY" && qty > 0 && reserve > freeCash;
  const overShares = side === "SELL" && qty > freeShares;
  const canSubmit = qty > 0 && !overCash && !overShares && !pending;

  // Several brokers often tie (every free-delivery broker costs the same on a
  // buy), so report how many share the lowest charge instead of implying the
  // alphabetical tie-break winner is uniquely cheapest.
  const cheapest = useMemo(() => {
    if (!leg || rankable.length === 0) return null;
    const costs = rankable.map((b) => ({ brand: b.brand, charges: legFor(side, lastClose, qty, b.fees).totalCharges }));
    const min = Math.min(...costs.map((c) => c.charges));
    const tied = costs.filter((c) => Math.abs(c.charges - min) < 0.005).sort((a, b) => a.brand.localeCompare(b.brand));
    return { brand: tied[0].brand, charges: min, others: tied.length - 1 };
  }, [leg, rankable, side, lastClose, qty]);

  const currentIsRankable = rankable.some((b) => b.id === currentBroker.id);
  const saving = leg && cheapest ? leg.totalCharges - cheapest.charges : 0;
  const estPnl = side === "SELL" && leg && avgCost !== null ? leg.turnover - leg.totalCharges - avgCost * qty : null;

  return (
    <form action={formAction} className="flex flex-col gap-5">
      <input type="hidden" name="symbol" value={symbol} />
      <input type="hidden" name="side" value={side} />
      <input type="hidden" name="clientOrderId" value={clientOrderId} />

      <div role="radiogroup" aria-label="Order side" className="grid grid-cols-2 gap-1 rounded-xl bg-sub p-1">
        {(["BUY", "SELL"] as const).map((s) => {
          const disabled = s === "SELL" && freeShares === 0;
          return (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={side === s}
              disabled={disabled}
              onClick={() => setSide(s)}
              title={disabled ? "You hold no free shares of this stock" : undefined}
              className={cx(
                "rounded-lg py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                side === s ? (s === "BUY" ? "bg-up text-invert" : "bg-down text-invert") : "text-muted hover:text-ink",
              )}
            >
              {s === "BUY" ? "Buy" : "Sell"}
            </button>
          );
        })}
      </div>

      <div>
        <label htmlFor="qty" className="mb-1.5 flex items-center justify-between text-sm">
          <span className="font-medium text-ink">Quantity (shares)</span>
          <span className="text-xs text-muted">
            {side === "BUY" ? (
              <>Up to <span className="num">{maxBuy.toLocaleString("en-IN")}</span> with free cash</>
            ) : (
              <><span className="num">{freeShares.toLocaleString("en-IN")}</span> free to sell</>
            )}
          </span>
        </label>
        <input
          id="qty"
          name="qty"
          inputMode="numeric"
          autoComplete="off"
          value={qtyText}
          onChange={(e) => setQtyText(e.target.value.replace(/[^\d]/g, "").slice(0, 7))}
          placeholder="0"
          aria-invalid={overCash || overShares}
          className={cx(
            "num w-full rounded-xl border bg-raised px-4 py-3 text-lg text-ink focus:outline-none",
            overCash || overShares ? "border-down" : "border-line-strong focus:border-accent",
          )}
        />
        <div className="mt-2 flex flex-wrap gap-2">
          {side === "BUY"
            ? BUY_SIZES.map((amt) => {
                const q = Math.min(Math.floor(amt / lastClose), maxBuy);
                return (
                  <button
                    key={amt}
                    type="button"
                    disabled={q < 1}
                    onClick={() => setQtyText(String(q))}
                    className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-accent hover:text-accent-ink disabled:opacity-40"
                  >
                    About {inrWhole(amt)}
                  </button>
                );
              })
            : [0.25, 0.5, 1].map((f) => {
                const q = Math.max(1, Math.floor(freeShares * f));
                return (
                  <button
                    key={f}
                    type="button"
                    disabled={freeShares === 0}
                    onClick={() => setQtyText(String(f === 1 ? freeShares : q))}
                    className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-accent hover:text-accent-ink disabled:opacity-40"
                  >
                    {f === 1 ? "All" : `${f * 100}%`}
                  </button>
                );
              })}
        </div>
        {overCash && (
          <p className="mt-2 text-sm text-down">
            That needs about {inr(reserve)} and you have {inr(freeCash)} free. The most you can buy is {maxBuy} shares.
          </p>
        )}
        {overShares && <p className="mt-2 text-sm text-down">You can sell at most {freeShares} shares right now.</p>}
      </div>

      <div className="rounded-xl border border-line bg-sub p-4 text-sm">
        <div className="mb-3 text-xs text-muted">
          Estimate at the {shortDate(props.lastCloseDate)} close of {inr(lastClose)} with {currentBroker.brand}&apos;s fees.
          The order fills at the {shortDate(props.targetTradeDate)} close, which will differ.
        </div>
        <dl className="grid grid-cols-2 gap-y-1.5">
          <dt className="text-muted">Order value</dt>
          <dd className="num text-right text-ink">{leg ? inr(leg.turnover) : "-"}</dd>
          <dt className="text-muted">Charges and taxes</dt>
          <dd className="num text-right text-ink">{leg ? inr(leg.totalCharges) : "-"}</dd>
          {side === "BUY" ? (
            <>
              <dt className="font-medium text-ink">Cash reserved now</dt>
              <dd className="num text-right font-medium text-ink">{leg ? inr(reserve) : "-"}</dd>
            </>
          ) : (
            <>
              <dt className="font-medium text-ink">You would receive</dt>
              <dd className="num text-right font-medium text-ink">{leg ? inr(leg.turnover - leg.totalCharges) : "-"}</dd>
              {estPnl !== null && (
                <>
                  <dt className="text-muted">P&amp;L on these shares</dt>
                  <dd className={cx("num text-right", pnlTone(estPnl))}>{signedInr(estPnl)}</dd>
                </>
              )}
            </>
          )}
        </dl>
        {leg && (
          <details className="mt-3 text-xs text-muted">
            <summary className="cursor-pointer select-none text-accent-ink">Itemised charges</summary>
            <dl className="mt-2 grid grid-cols-2 gap-y-1">
              <dt>Brokerage</dt>
              <dd className="num text-right">{inr(leg.brokerage)}</dd>
              <dt>STT (0.1%)</dt>
              <dd className="num text-right">{inr(leg.stt)}</dd>
              <dt>Exchange and SEBI fees</dt>
              <dd className="num text-right">{inr(leg.exchangeCharges + leg.sebiCharges)}</dd>
              <dt>Stamp duty (buy only)</dt>
              <dd className="num text-right">{inr(leg.stampDuty)}</dd>
              <dt>GST (18%)</dt>
              <dd className="num text-right">{inr(leg.gst)}</dd>
              <dt>DP charge (sell only)</dt>
              <dd className="num text-right">{inr(leg.dpCharge)}</dd>
            </dl>
            {side === "BUY" && (
              <p className="mt-2">
                Cash reserved includes {PRICE_MOVE_BUFFER_PCT * 100}% headroom for the price moving before the fill. Anything
                unused stays in your balance.
              </p>
            )}
          </details>
        )}
      </div>

      {leg && cheapest && (
        <div className="rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-ink">
          {saving >= 1 ? (
            <>
              The same order would cost <span className="num font-semibold">{inr(cheapest.charges)}</span> in charges at{" "}
              <span className="font-semibold">{cheapest.brand}</span>
              {cheapest.others > 0 && ` and ${cheapest.others} other ${cheapest.others === 1 ? "broker" : "brokers"} with the same charge`},{" "}
              <span className="num">{inr(saving)}</span> less than at {currentBroker.brand}.{" "}
              <Link href="/costs" className="font-medium text-accent-ink underline-offset-2 hover:underline">
                Compare brokers for your trades
              </Link>
            </>
          ) : currentIsRankable ? (
            <>
              {currentBroker.brand} has the lowest charges for this order among the {rankable.length} brokers with a full
              fee schedule on file.
            </>
          ) : (
            <>
              Lowest charges for this order among the {rankable.length} fully documented brokers: {cheapest.brand} at{" "}
              <span className="num">{inr(cheapest.charges)}</span>.
            </>
          )}
        </div>
      )}

      {state.status === "ok" && (
        <Notice tone="up">
          {state.message} It fills at the {shortDate(state.targetTradeDate)} close, once NSE publishes it that evening.{" "}
          <Link href="/orders" className="font-medium text-accent-ink underline-offset-2 hover:underline">
            Track it in Orders
          </Link>
        </Notice>
      )}
      {state.status === "error" && <Notice tone="down">{state.message}</Notice>}

      <button type="submit" disabled={!canSubmit} className={cx(buttonClass("primary"), "py-3 text-base")}>
        {pending ? "Placing order" : side === "BUY" ? "Place buy order" : "Place sell order"}
      </button>
    </form>
  );
}

"use client";

import { useActionState, useMemo, useState } from "react";
import Link from "next/link";
import { placeOrderAction, type OrderActionState } from "@/app/(app)/actions";
import { buyLegFor, PRICE_MOVE_BUFFER_PCT, sellLegFor, type DeliveryFees, type LegCharges } from "@/lib/trade-costs";
import {
  buyReserve,
  GTT_DAYS,
  maxBuyQty,
  ORDER_TYPE_LABEL,
  priceTermsError,
  type OrderType,
  type Validity,
} from "@/lib/fills";
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
  // True when the practice market's session is not open right now, so the
  // order is in before its session opens and a market order takes the open.
  beforeOpen: boolean;
  // Idempotency key generated on the server for this render.
  clientOrderId: string;
}

const INITIAL: OrderActionState = { status: "idle", message: "" };
const BUY_SIZES = [10_000, 25_000, 50_000, 1_00_000];

function addDays(iso: string, days: number): string {
  return new Date(new Date(`${iso}T00:00:00Z`).getTime() + days * 86_400_000).toISOString().slice(0, 10);
}

/** One plain sentence on when, and at what price, this order would fill. */
function fillSentence(side: "BUY" | "SELL", type: OrderType, price: number | null, validity: Validity, beforeOpen: boolean, target: string) {
  const day = shortDate(target);
  const when = validity === "GTT" ? `on any session from ${day} to ${shortDate(addDays(target, GTT_DAYS))}` : `on ${day}`;
  if (type === "MARKET") {
    return beforeOpen
      ? `After-market order: fills at the ${day} open (9:15).`
      : `Fills at today's ${day} close (15:30). This practice market has each day's open, high, low and close, not every tick.`;
  }
  if (price === null) return "Enter a price to see when it fills.";
  if (type === "LIMIT") {
    return side === "BUY"
      ? `Buys at ${inr(price)} or lower if the price trades below ${inr(price)} ${when}.${beforeOpen ? " If the session opens below it, you get the open." : ""}`
      : `Sells at ${inr(price)} or higher if the price trades above ${inr(price)} ${when}.${beforeOpen ? " If the session opens above it, you get the open." : ""}`;
  }
  return side === "SELL"
    ? `Sells at market if the price falls to ${inr(price)} ${when}. A gap below the trigger fills at the lower open.`
    : `Buys at market if the price rises to ${inr(price)} ${when}. A gap above the trigger fills at the higher open.`;
}

function legFor(side: "BUY" | "SELL", price: number, qty: number, fees: DeliveryFees): LegCharges {
  return side === "BUY" ? buyLegFor(price, qty, fees) : sellLegFor(price, qty, fees);
}

export function OrderTicket(props: Props) {
  const { symbol, lastClose, currentBroker, rankable, freeCash, freeShares, avgCost } = props;
  const [side, setSide] = useState<"BUY" | "SELL">(props.defaultSide === "SELL" && freeShares > 0 ? "SELL" : "BUY");
  const [qtyText, setQtyText] = useState("");
  const [orderType, setOrderType] = useState<OrderType>("MARKET");
  const [validity, setValidity] = useState<Validity>("DAY");
  const [priceText, setPriceText] = useState(lastClose.toFixed(2));
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
  const needsPrice = orderType !== "MARKET";
  const enteredPrice = needsPrice && /^\d+(\.\d{0,2})?$/.test(priceText) ? Number(priceText) : null;
  const limitPrice = orderType === "LIMIT" ? enteredPrice : null;
  const triggerPrice = orderType === "SL_M" ? enteredPrice : null;
  const termsError = needsPrice ? priceTermsError(side, orderType, limitPrice, triggerPrice, lastClose) : null;
  // Estimates use the price the order is most likely to fill at.
  const estPrice = enteredPrice ?? lastClose;
  const maxBuy = useMemo(
    () => maxBuyQty(orderType, lastClose, limitPrice, triggerPrice, freeCash, currentBroker.fees),
    [orderType, lastClose, limitPrice, triggerPrice, freeCash, currentBroker.fees],
  );
  const leg = qty > 0 ? legFor(side, estPrice, qty, currentBroker.fees) : null;
  const reserve = side === "BUY" && qty > 0 ? buyReserve(orderType, lastClose, limitPrice, triggerPrice, qty, currentBroker.fees) : 0;

  const overCash = side === "BUY" && qty > 0 && reserve > freeCash;
  const overShares = side === "SELL" && qty > freeShares;
  const canSubmit = qty > 0 && !overCash && !overShares && !termsError && !pending;

  const chooseType = (t: OrderType) => {
    setOrderType(t);
    if (t === "MARKET") setValidity("DAY");
    // Start a stop a little beyond the last close, on the side it must sit.
    const start = t === "SL_M" ? lastClose * (side === "SELL" ? 0.97 : 1.03) : lastClose;
    setPriceText(start.toFixed(2));
  };
  const chooseSide = (s: "BUY" | "SELL") => {
    setSide(s);
    if (orderType === "SL_M") setPriceText((lastClose * (s === "SELL" ? 0.97 : 1.03)).toFixed(2));
  };

  // Several brokers often tie (every free-delivery broker costs the same on a
  // buy), so report how many share the lowest charge instead of implying the
  // alphabetical tie-break winner is uniquely cheapest.
  const cheapest = useMemo(() => {
    if (!leg || rankable.length === 0) return null;
    const costs = rankable.map((b) => ({ brand: b.brand, charges: legFor(side, estPrice, qty, b.fees).totalCharges }));
    const min = Math.min(...costs.map((c) => c.charges));
    const tied = costs.filter((c) => Math.abs(c.charges - min) < 0.005).sort((a, b) => a.brand.localeCompare(b.brand));
    return { brand: tied[0].brand, charges: min, others: tied.length - 1 };
  }, [leg, rankable, side, estPrice, qty]);

  const currentIsRankable = rankable.some((b) => b.id === currentBroker.id);
  const saving = leg && cheapest ? leg.totalCharges - cheapest.charges : 0;
  const estPnl = side === "SELL" && leg && avgCost !== null ? leg.turnover - leg.totalCharges - avgCost * qty : null;

  return (
    <form action={formAction} className="flex flex-col gap-5">
      <input type="hidden" name="symbol" value={symbol} />
      <input type="hidden" name="side" value={side} />
      <input type="hidden" name="clientOrderId" value={clientOrderId} />
      <input type="hidden" name="orderType" value={orderType} />
      <input type="hidden" name="validity" value={validity} />
      {orderType === "LIMIT" && <input type="hidden" name="limitPrice" value={priceText} />}
      {orderType === "SL_M" && <input type="hidden" name="triggerPrice" value={priceText} />}

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
              onClick={() => chooseSide(s)}
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

      <div role="radiogroup" aria-label="Order type" className="flex gap-1 text-sm">
        {(["MARKET", "LIMIT", "SL_M"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="radio"
            aria-checked={orderType === t}
            onClick={() => chooseType(t)}
            className={cx(
              "flex-1 rounded-lg border px-3 py-1.5 font-medium transition-colors",
              orderType === t ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-muted hover:text-ink",
            )}
          >
            {ORDER_TYPE_LABEL[t]}
          </button>
        ))}
      </div>

      {needsPrice && (
        <div>
          <label htmlFor="price" className="mb-1.5 flex items-center justify-between text-sm">
            <span className="font-medium text-ink">{orderType === "LIMIT" ? "Limit price" : "Trigger price"}</span>
            <span className="text-xs text-muted">Last close {inr(lastClose)}</span>
          </label>
          <input
            id="price"
            inputMode="decimal"
            autoComplete="off"
            value={priceText}
            onChange={(e) => setPriceText(e.target.value.replace(/[^\d.]/g, "").slice(0, 10))}
            aria-invalid={termsError !== null}
            className={cx(
              "num w-full rounded-xl border bg-raised px-4 py-3 text-lg text-ink focus:outline-none",
              termsError ? "border-down" : "border-line-strong focus:border-accent",
            )}
          />
          {termsError && <p className="mt-2 text-sm text-down">{termsError}</p>}
        </div>
      )}

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

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="font-medium text-ink">Validity</span>
        {(["DAY", "GTT"] as const).map((v) => {
          const disabled = v === "GTT" && orderType === "MARKET";
          return (
            <label key={v} className={cx("inline-flex items-center gap-1.5", disabled ? "text-faint" : "text-ink")}>
              <input
                type="radio"
                name="validity-choice"
                checked={validity === v}
                disabled={disabled}
                onChange={() => setValidity(v)}
                className="accent-[var(--accent)]"
              />
              {v === "DAY" ? "Day" : "GTT, up to 1 year"}
            </label>
          );
        })}
        {orderType === "MARKET" && <span className="text-xs text-muted">GTT needs a limit or stop-loss price</span>}
      </div>

      <p className="rounded-lg bg-accent-soft px-3 py-2 text-sm text-ink">
        {fillSentence(side, orderType, enteredPrice, validity, props.beforeOpen, props.targetTradeDate)}
      </p>

      <div className="rounded-xl border border-line bg-sub p-4 text-sm">
        <div className="mb-3 text-xs text-muted">
          Estimate at {needsPrice && enteredPrice ? `your ${orderType === "LIMIT" ? "limit" : "trigger"} of ${inr(estPrice)}` : `the ${shortDate(props.lastCloseDate)} close of ${inr(lastClose)}`}{" "}
          with {currentBroker.brand}&apos;s fees. The actual fill price will differ.
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
                {orderType === "LIMIT"
                  ? "Cash reserved is the cost at your limit price, the most this order can pay."
                  : `Cash reserved includes ${PRICE_MOVE_BUFFER_PCT * 100}% headroom for the price moving before the fill.`}{" "}
                Anything unused stays in your balance.
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
          {state.message} Its first chance to fill is the {shortDate(state.targetTradeDate)} session.{" "}
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

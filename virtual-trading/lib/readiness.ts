// "Before you invest for real" checklist. Every milestone is derived from the
// account's own simulated history; none rewards trading volume or profit.
// They mark habits worth having before real money is involved: seeing how
// costs work on both legs of a trade, and not concentrating in one stock.

import { MIN_TRADES_FOR_SCORE } from "./scoring";

export interface ReadinessInput {
  ordersPlaced: number;
  ordersFilled: number;
  closedTrades: number;
  holdingsCount: number;
  // Largest single holding's share of total holdings value, 0 to 1. Null
  // when there are no holdings.
  largestHoldingWeight: number | null;
}

export interface Milestone {
  id: "first_order" | "first_fill" | "round_trip" | "diversified" | "score_unlocked";
  title: string;
  detail: string;
  done: boolean;
}

export const DIVERSIFIED_MIN_HOLDINGS = 3;
export const DIVERSIFIED_MAX_WEIGHT = 0.5;

export function readinessMilestones(input: ReadinessInput): Milestone[] {
  const diversified =
    input.holdingsCount >= DIVERSIFIED_MIN_HOLDINGS &&
    input.largestHoldingWeight !== null &&
    input.largestHoldingWeight <= DIVERSIFIED_MAX_WEIGHT;

  return [
    {
      id: "first_order",
      title: "Place your first order",
      detail: "See how an order waits for the next official NSE close instead of filling instantly.",
      done: input.ordersPlaced > 0,
    },
    {
      id: "first_fill",
      title: "Get your first fill",
      detail: "Your order settles at a real closing price, with every charge itemised.",
      done: input.ordersFilled > 0,
    },
    {
      id: "round_trip",
      title: "Complete a round trip",
      detail: "Buy, then sell. STT applies to both legs, stamp duty to the buy, the DP charge to the sell.",
      done: input.closedTrades > 0,
    },
    {
      id: "diversified",
      title: `Hold ${DIVERSIFIED_MIN_HOLDINGS} or more stocks, none above half your invested value`,
      detail: "A basic habit that limits how much one company can move your whole portfolio.",
      done: diversified,
    },
    {
      id: "score_unlocked",
      title: `Close ${MIN_TRADES_FOR_SCORE} trades`,
      detail: "Enough history for a confidence score that reflects more than one lucky or unlucky trade.",
      done: input.closedTrades >= MIN_TRADES_FOR_SCORE,
    },
  ];
}

export function readinessProgress(milestones: Milestone[]): { done: number; total: number; ready: boolean } {
  const done = milestones.filter((m) => m.done).length;
  return { done, total: milestones.length, ready: done === milestones.length };
}

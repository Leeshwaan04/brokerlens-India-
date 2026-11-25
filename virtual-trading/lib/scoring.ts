// "Trading Confidence Score": one honest, composite 0-100 number computed
// only from this account's own real simulated trade history. No external
// benchmarking, no certification tiers, no claim of future performance. Below
// MIN_TRADES_FOR_SCORE closed trades, the score is not meaningful yet and the
// caller should show "not enough trades yet" instead of this number.

export const MIN_TRADES_FOR_SCORE = 5;

export interface ScoreInput {
  totalReturnPct: number;
  numClosedTrades: number;
  winRate: number | null; // fraction 0..1, null until numClosedTrades >= MIN_TRADES_FOR_SCORE
  largestHoldingValue: number;
  portfolioValue: number;
}

export type ScoreLabel = "Building Track Record" | "Developing" | "Consistent" | "Strong";

export interface ScoreComponents {
  base: number;
  returnTerm: number;
  consistencyTerm: number;
  concentrationPenalty: number;
  experienceBonus: number;
}

export interface ScoreResult {
  score: number;
  label: ScoreLabel;
  enoughTrades: boolean;
  // Each term of the formula, so the UI can show how the number was built.
  components: ScoreComponents;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

function labelFor(score: number): ScoreLabel {
  if (score < 40) return "Building Track Record";
  if (score < 60) return "Developing";
  if (score < 80) return "Consistent";
  return "Strong";
}

export function computeConfidenceScore(input: ScoreInput): ScoreResult {
  const enoughTrades = input.numClosedTrades >= MIN_TRADES_FOR_SCORE;
  const concentration = input.portfolioValue > 0 ? input.largestHoldingValue / input.portfolioValue : 0;

  const returnTerm = 20 * clamp(input.totalReturnPct / 25, -1, 1);
  const consistencyTerm = enoughTrades && input.winRate !== null ? 20 * clamp((input.winRate - 0.5) * 2, -1, 1) : 0;
  const concentrationPenalty = 15 * clamp((concentration - 0.5) / 0.5, 0, 1);
  const experienceBonus = 10 * clamp(input.numClosedTrades / 20, 0, 1);

  const raw = 50 + returnTerm + consistencyTerm - concentrationPenalty + experienceBonus;
  const score = clamp(Math.round(raw), 0, 100);

  return {
    score,
    label: labelFor(score),
    enoughTrades,
    components: { base: 50, returnTerm, consistencyTerm, concentrationPenalty, experienceBonus },
  };
}

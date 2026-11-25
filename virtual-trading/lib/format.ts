// One place for how money, dates and percentages read across the app, so a
// figure never appears as "Rs 1363.00" on one page and "₹1,363.00" on another.

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const INR_WHOLE = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function inr(n: number): string {
  return INR.format(n);
}

export function inrWhole(n: number): string {
  return INR_WHOLE.format(n);
}

/** "+₹1,234.50" / "-₹1,234.50", for P&L where the sign is the point. */
export function signedInr(n: number): string {
  const s = INR.format(Math.abs(n));
  if (Math.abs(n) < 0.005) return INR.format(0);
  return n > 0 ? `+${s}` : `-${s}`;
}

export function signedPct(n: number, digits = 2): string {
  const s = Math.abs(n).toFixed(digits);
  if (Number(s) === 0) return `${(0).toFixed(digits)}%`;
  return n > 0 ? `+${s}%` : `-${s}%`;
}

/** "2026-11-18" (a Postgres date column) to "18 Nov 2026". */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function pnlTone(n: number | null): string {
  if (n === null || Math.abs(n) < 0.005) return "text-muted";
  return n > 0 ? "text-up" : "text-down";
}

import { inr, shortDate } from "@/lib/format";

export interface ClosePoint {
  date: string;
  close: number;
}

const W = 640;
const H = 160;
const PAD = { top: 14, right: 8, bottom: 20, left: 8 };

// Official closes for the sessions on file, oldest to newest, as an inline
// SVG. Like EquityChart, the axis never zooms tighter than a 4% band, so a
// quiet stretch is not drawn as a swing.
export function PriceChart({ points, symbol }: { points: ClosePoint[]; symbol: string }) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.close);
  const last = points[points.length - 1];
  let min = Math.min(...values);
  let max = Math.max(...values);
  const minSpan = last.close * 0.04;
  if (max - min < minSpan) {
    const mid = (max + min) / 2;
    min = mid - minSpan / 2;
    max = mid + minSpan / 2;
  }
  const span = max - min || 1;
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - min) / span) * (H - PAD.top - PAD.bottom);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - PAD.bottom} L${x(0).toFixed(1)},${H - PAD.bottom} Z`;
  const up = last.close >= points[0].close;
  const stroke = up ? "var(--up)" : "var(--down)";
  const hi = Math.max(...values);
  const lo = Math.min(...values);
  const title = `${symbol} official closes over ${points.length} sessions, ${shortDate(points[0].date)} to ${shortDate(last.date)}: from ${inr(points[0].close)} to ${inr(last.close)}, high ${inr(hi)}, low ${inr(lo)}.`;
  const gradientId = `price-fill-${symbol}`;

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-labelledby={`${gradientId}-title`}>
        <title id={`${gradientId}-title`}>{title}</title>
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.18" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${gradientId})`} />
        <path d={line} fill="none" stroke={stroke} strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(points.length - 1)} cy={y(last.close)} r="3" fill={stroke} />
        <text x={PAD.left} y={H - 5} fontSize="10" fill="var(--text-faint)">
          {shortDate(points[0].date)}
        </text>
        <text x={W - PAD.right} y={H - 5} fontSize="10" fill="var(--text-faint)" textAnchor="end">
          {shortDate(last.date)}
        </text>
      </svg>
      <figcaption className="mt-1 flex flex-wrap justify-between gap-2 text-xs text-muted">
        <span>
          Closes, last {points.length} sessions
        </span>
        <span className="num">
          High {inr(hi)} · Low {inr(lo)}
        </span>
      </figcaption>
    </figure>
  );
}

import { inrWhole, shortDate } from "@/lib/format";

export interface EquityPoint {
  date: string;
  value: number;
}

const W = 640;
const H = 200;
const PAD = { top: 12, right: 8, bottom: 24, left: 8 };

// Portfolio value at each ingested close, drawn as an inline SVG area chart
// with a dashed line at the starting balance. Server-rendered, no chart
// library, no client JavaScript.
export function EquityChart({
  points,
  startingBalance,
  benchmark,
}: {
  points: EquityPoint[];
  startingBalance: number;
  /** The index's move on the same scale (lib/index-data.ts benchmarkPoints), drawn as a dotted line. */
  benchmark?: { label: string; points: EquityPoint[] } | null;
}) {
  if (points.length < 2) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg bg-sub px-6 text-center text-sm text-muted">
        Your portfolio value is recorded at every daily close. The chart appears after the next one.
      </div>
    );
  }
  const values = [...points.map((p) => p.value), ...(benchmark?.points.map((p) => p.value) ?? [])];
  let min = Math.min(...values, startingBalance);
  let max = Math.max(...values, startingBalance);
  // Never let the axis auto-zoom below a 4% band (±2% of the starting
  // balance): fitted tightly to the data, a 0.3% dip is drawn as a crash,
  // which is exactly how charts mislead beginners.
  const minSpan = startingBalance * 0.04;
  if (max - min < minSpan) {
    const mid = (max + min) / 2;
    min = mid - minSpan / 2;
    max = mid + minSpan / 2;
  }
  const span = max - min || 1;
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - min) / span) * (H - PAD.top - PAD.bottom);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - PAD.bottom} L${x(0).toFixed(1)},${H - PAD.bottom} Z`;
  const dateIndex = new Map(points.map((p, i) => [p.date, i]));
  // Needs at least two dates, or the line is a point and the caption would describe nothing visible.
  const benchLine = benchmark && dateIndex.size >= 2
    ? benchmark.points
        .filter((p) => dateIndex.has(p.date))
        .map((p, i) => `${i === 0 ? "M" : "L"}${x(dateIndex.get(p.date)!).toFixed(1)},${y(p.value).toFixed(1)}`)
        .join(" ")
    : "";
  const last = points[points.length - 1];
  const up = last.value >= startingBalance;
  const stroke = up ? "var(--up)" : "var(--down)";
  // One string child: React 19 mismatches a <title> built from several text nodes.
  const title = `Portfolio value from ${shortDate(points[0].date)} to ${shortDate(last.date)}, now ${inrWhole(last.value)} against a start of ${inrWhole(startingBalance)}.`;

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-labelledby="equity-title">
        <title id="equity-title">{title}</title>
        <defs>
          <linearGradient id="equity-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={PAD.left} x2={W - PAD.right} y1={y(startingBalance)} y2={y(startingBalance)} stroke="var(--border-strong)" strokeDasharray="4 4" />
        <path d={area} fill="url(#equity-fill)" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {benchLine && <path d={benchLine} fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="1 4" strokeLinecap="round" />}
        <circle cx={x(points.length - 1)} cy={y(last.value)} r="3.5" fill={stroke} />
        <text x={PAD.left + 4} y={PAD.top + 10} fontSize="10" fill="var(--text-faint)">
          {inrWhole(max)}
        </text>
        <text x={PAD.left + 4} y={H - PAD.bottom - 4} fontSize="10" fill="var(--text-faint)">
          {inrWhole(min)}
        </text>
        <text x={PAD.left} y={H - 6} fontSize="11" fill="var(--text-faint)">
          {shortDate(points[0].date)}
        </text>
        <text x={W - PAD.right} y={H - 6} fontSize="11" fill="var(--text-faint)" textAnchor="end">
          {shortDate(last.date)}
        </text>
      </svg>
      <figcaption className="mt-1 text-xs text-muted">
        Dashed line: your starting balance of {inrWhole(startingBalance)}.
        {benchLine && benchmark && <> Dotted line: what {inrWhole(startingBalance)} would have done in the {benchmark.label}, over the same dates.</>}
      </figcaption>
    </figure>
  );
}

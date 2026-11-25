import Link from "next/link";
import type { Milestone } from "@/lib/readiness";
import { goHref } from "@/lib/brokers";
import { buttonClass, Card, CardTitle, cx } from "./ui";

function Check({ done }: { done: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold",
        done ? "border-up bg-up text-invert" : "border-line-strong text-transparent",
      )}
    >
      ✓
    </span>
  );
}

export function ReadinessCard({
  milestones,
  progress,
  brokerId,
  brokerBrand,
}: {
  milestones: Milestone[];
  progress: { done: number; total: number; ready: boolean };
  brokerId: string;
  brokerBrand: string;
}) {
  const pct = Math.round((progress.done / progress.total) * 100);
  return (
    <Card>
      <CardTitle action={<span className="num text-sm text-muted">{progress.done} of {progress.total}</span>}>
        Before you invest for real
      </CardTitle>
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-sub" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-up transition-all" style={{ width: `${pct}%` }} />
      </div>
      <ul className="flex flex-col gap-3">
        {milestones.map((m) => (
          <li key={m.id} className="flex gap-3">
            <Check done={m.done} />
            <div>
              <div className={cx("text-sm font-medium", m.done ? "text-muted line-through decoration-line-strong" : "text-ink")}>
                {m.title}
              </div>
              {!m.done && <div className="text-xs text-muted">{m.detail}</div>}
            </div>
          </li>
        ))}
      </ul>
      {progress.ready && (
        <div className="mt-5 rounded-lg border border-up/30 bg-up-soft p-4">
          <p className="text-sm font-medium text-ink">You have practised the basics.</p>
          <p className="mt-1 text-xs text-muted">
            Practice is not a guarantee of real results. If you decide to invest real money, check which broker would
            have charged you least for the way you trade.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/costs" className={buttonClass("primary", "sm")}>
              Compare brokers for my trades
            </Link>
            <a href={goHref(brokerId, "readiness")} target="_blank" rel="noopener sponsored nofollow" className={buttonClass("secondary", "sm")}>
              Open a {brokerBrand} account
            </a>
          </div>
        </div>
      )}
    </Card>
  );
}

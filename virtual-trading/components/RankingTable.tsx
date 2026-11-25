import type { RankedBroker } from "@/lib/cost-replay";
import { goHref, type BrokerRow } from "@/lib/brokers";
import type { CtaPlacement } from "@/lib/schema";
import { switchBrokerAction } from "@/app/(app)/actions";
import { inr, signedInr } from "@/lib/format";
import { buttonClass, cx, Pill } from "./ui";

// Brokers ranked by what the same trades cost at each, cheapest first. The
// order comes only from rankBrokersForFills (cost, then name), never from
// partner status, and every row gets the same "open an account" link.
export function RankingTable({
  rows,
  brokers,
  placement,
  currentId,
  baselineTotal,
  allowSwitch = false,
}: {
  rows: RankedBroker[];
  brokers: Map<string, BrokerRow>;
  placement: CtaPlacement;
  currentId?: string;
  baselineTotal?: number;
  allowSwitch?: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[900px] text-sm">
        <thead className="whitespace-nowrap bg-sub text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="px-4 py-3 font-medium">#</th>
            <th className="px-4 py-3 font-medium">Broker</th>
            <th className="px-4 py-3 text-right font-medium">Brokerage</th>
            <th className="px-4 py-3 text-right font-medium">DP charges</th>
            <th className="px-4 py-3 text-right font-medium">Taxes and fees</th>
            <th className="px-4 py-3 text-right font-medium">Total</th>
            {baselineTotal !== undefined && <th className="px-4 py-3 text-right font-medium">vs yours</th>}
            <th className="px-4 py-3 font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line whitespace-nowrap bg-raised">
          {rows.map((r) => {
            const b = brokers.get(r.id);
            const isCurrent = r.id === currentId;
            const diff = baselineTotal !== undefined ? r.totalCharges - baselineTotal : 0;
            return (
              <tr key={r.id} className={cx(isCurrent && "bg-accent-soft/60", r.rank === 1 && !isCurrent && "bg-up-soft/50")}>
                <td className="num px-4 py-3 text-muted">{r.rank}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium text-ink">{r.brand}</span>
                    {r.rank === 1 && <Pill tone="up">Lowest cost</Pill>}
                    {isCurrent && <Pill tone="accent">Your practice broker</Pill>}
                    {b && !b.feeScheduleComplete && <Pill tone="warn">Indicative</Pill>}
                  </div>
                  {b?.dematAmc != null && Number(b.dematAmc) > 0 && (
                    <div className="num mt-0.5 text-xs text-muted">Plus {inr(Number(b.dematAmc))} a year demat AMC</div>
                  )}
                </td>
                <td className="num px-4 py-3 text-right text-ink">{inr(r.brokerage)}</td>
                <td className="num px-4 py-3 text-right text-ink">{inr(r.dpCharges)}</td>
                <td className="num px-4 py-3 text-right text-ink">{inr(r.taxesAndFees)}</td>
                <td className="num px-4 py-3 text-right font-semibold text-ink">{inr(r.totalCharges)}</td>
                {baselineTotal !== undefined && (
                  <td className={cx("num px-4 py-3 text-right", diff < -0.005 ? "text-up" : diff > 0.005 ? "text-down" : "text-muted")}>
                    {isCurrent ? "-" : signedInr(diff)}
                  </td>
                )}
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2 whitespace-nowrap">
                    {allowSwitch && !isCurrent && (
                      <form action={switchBrokerAction}>
                        <input type="hidden" name="brokerId" value={r.id} />
                        <input type="hidden" name="returnTo" value="/costs" />
                        <button type="submit" className={buttonClass("ghost", "sm")}>
                          Practise with
                        </button>
                      </form>
                    )}
                    <a
                      href={goHref(r.id, placement)}
                      target="_blank"
                      rel="noopener sponsored nofollow"
                      className={buttonClass(r.rank === 1 ? "primary" : "secondary", "sm")}
                    >
                      Open account
                    </a>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

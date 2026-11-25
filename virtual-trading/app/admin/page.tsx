import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { Card, CardTitle, cx, Notice, PageHeader, Stat } from "@/components/ui";
import { getAdminMetrics, isAdmin, PERIODS } from "@/lib/admin-metrics";
import { shortDate } from "@/lib/format";
import { getSessionUserId } from "@/lib/session";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

const REJECTION_LABELS: Record<string, string> = {
  insufficient_cash: "Not enough free cash",
  insufficient_shares: "Selling shares not held",
  invalid_qty: "Invalid quantity",
  qty_too_large: "Quantity over the limit",
  invalid_side: "No side chosen",
  not_available: "Stock not in the universe",
  no_price: "No price on file",
  broker_missing: "Practice broker missing",
  no_account: "No practice account",
  error: "Unexpected error",
  other: "Other",
};

const PLACEMENT_LABELS: Record<string, string> = {
  landing: "Landing page",
  replay: "Cost replay",
  ticket: "Order ticket",
  broker: "Broker page",
  dashboard: "Dashboard",
  readiness: "Readiness card",
  onboarding: "Onboarding",
  other: "Other",
};

const fmt = (v: number) => v.toLocaleString("en-IN");
const plural = (v: number, one: string, many: string) => `${fmt(v)} ${v === 1 ? one : many}`;
const pct = (part: number, whole: number) => (whole > 0 ? `${Math.round((part / whole) * 100)}%` : "–");

function Table({ head, rows, empty }: { head: string[]; rows: (string | number)[][]; empty: string }) {
  if (rows.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            {head.map((h, i) => (
              <th key={h} className={cx("py-2 font-medium", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {r.map((c, j) => (
                <td key={j} className={cx("py-2", j === 0 ? "text-ink" : "num text-right text-muted")}>
                  {typeof c === "number" ? fmt(c) : c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Private: only user ids listed in ADMIN_USER_IDS see it; everyone else gets
// the normal 404, so the page does not advertise that it exists.
export default async function AdminPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const userId = await getSessionUserId();
  if (!isAdmin(userId)) notFound();

  const { days: rawDays } = await searchParams;
  const days = PERIODS.find((p) => p === Number(rawDays)) ?? 30;
  const m = await getAdminMetrics(days);

  const lastRun = m.cronRuns[0];
  const hoursSinceOk = m.hoursSinceLastOkSync ?? Infinity;
  const top = m.funnel[0].value;

  return (
    <>
      <AppHeader signedIn />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <PageHeader
          title="Admin"
          subtitle="First-party counts from this app's own database. No personal details are shown here."
          action={
            <div className="flex gap-1 rounded-lg border border-line bg-raised p-1 text-sm">
              {PERIODS.map((p) => (
                <Link
                  key={p}
                  href={`/admin?days=${p}`}
                  className={cx("rounded-md px-3 py-1", p === days ? "bg-accent-soft font-medium text-accent-ink" : "text-muted hover:text-ink")}
                >
                  {p} days
                </Link>
              ))}
            </div>
          }
        />

        {hoursSinceOk > 30 && (
          <div className="mb-6">
            <Notice tone="warn">
              No successful price sync in the last {Number.isFinite(hoursSinceOk) ? `${Math.floor(hoursSinceOk)} hours` : "record"}.
              Pending orders will not fill until it runs. Check the EOD sync workflow.
            </Notice>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Accounts" value={fmt(m.active.total)} sub="All practice accounts" />
          <Stat label="Active today" value={fmt(m.active.dau)} sub="India time" />
          <Stat label="Active, 7 days" value={fmt(m.active.wau)} sub={`${pct(m.active.wau, m.active.total)} of accounts`} />
          <Stat label="Active, 30 days" value={fmt(m.active.mau)} sub={`${pct(m.active.mau, m.active.total)} of accounts`} />
        </div>

        <Card className="mt-6">
          <CardTitle>Funnel, last {days} days</CardTitle>
          <ol className="flex flex-col gap-3">
            {m.funnel.map((s) => (
              <li key={s.step}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-ink">{s.step}</span>
                  <span className="num text-ink">
                    {fmt(s.value)} <span className="text-xs text-muted">{s === m.funnel[0] ? "" : pct(s.value, top)}</span>
                  </span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-sub">
                  <div className="h-2 rounded-full bg-accent" style={{ width: top > 0 ? `${Math.max(1, (s.value / top) * 100)}%` : "0%" }} />
                </div>
                {s.note && <p className="mt-1 text-xs text-muted">{s.note}</p>}
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs text-faint">
            Steps are counted independently over the period, not as one cohort, so a later step can exceed an earlier one.
            Accounts deleted since, and orders cleared by a portfolio reset, drop out of the per-account steps.
          </p>
        </Card>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Card>
            <CardTitle>Account-opening clicks by placement</CardTitle>
            <Table
              head={["Placement", "Clicks"]}
              rows={m.byPlacement.map((r) => [PLACEMENT_LABELS[r.placement] ?? r.placement, r.clicks])}
              empty="No clicks in this period."
            />
          </Card>
          <Card>
            <CardTitle>Account-opening clicks by broker</CardTitle>
            <Table head={["Broker", "Clicks"]} rows={m.byBroker.map((r) => [r.brand, r.clicks])} empty="No clicks in this period." />
          </Card>
          <Card>
            <CardTitle>Where visitors came from</CardTitle>
            <Table
              head={["utm_source", "Landing views", "Accounts"]}
              rows={m.sources.map((r) => [r.source ?? "Untagged", r.landings, r.signups])}
              empty="No visits in this period."
            />
            <p className="mt-3 text-xs text-faint">
              Only links carrying utm_source are attributed. Tag links from brokerlens.in, newsletters and social posts.
            </p>
          </Card>
          <Card>
            <CardTitle>Orders</CardTitle>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Placed" value={fmt(m.orders.placed)} />
              <Stat label="Filled" value={fmt(m.orders.filled)} />
              <Stat label="Waiting" value={fmt(m.orders.pending)} />
              <Stat label="Rejected at fill" value={fmt(m.orders.rejected)} />
              <Stat label="Cancelled" value={fmt(m.orders.cancelled)} />
              <Stat label="Broker switches" value={fmt(m.accountActions.brokerSwitches)} />
            </div>
            <p className="mt-3 text-xs text-muted">
              {plural(m.accountActions.resets, "portfolio reset", "portfolio resets")} and{" "}
              {plural(m.accountActions.deletions, "account deletion", "account deletions")} in this period.
            </p>
          </Card>
          <Card>
            <CardTitle>Orders the ticket refused</CardTitle>
            <Table
              head={["Reason", "Times"]}
              rows={m.ticketRejections.map((r) => [REJECTION_LABELS[r.reason] ?? r.reason, r.total])}
              empty="No refused orders in this period."
            />
          </Card>
          <Card>
            <CardTitle>Price sync runs</CardTitle>
            <Table
              head={["Run (IST)", "Close date", "Rows", "Status"]}
              rows={m.cronRuns.map((r) => [
                r.runAt.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }),
                shortDate(r.tradeDate),
                r.rowsIngested ?? 0,
                r.status,
              ])}
              empty="The price sync has never run."
            />
            {lastRun?.error && <p className="mt-3 break-words text-xs text-down">Last error: {lastRun.error}</p>}
          </Card>
        </div>

        <Card className="mt-6">
          <CardTitle>Last 14 days</CardTitle>
          <Table
            head={["Day", "Landing views", "Accounts created", "Orders", "Account-opening clicks"]}
            rows={m.daily
              .slice()
              .reverse()
              .map((d) => [shortDate(d.day), d.landings, d.signups, d.orders, d.clicks])}
            empty=""
          />
        </Card>
      </main>
      <SiteFooter />
    </>
  );
}

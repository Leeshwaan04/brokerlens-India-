import type { ReactNode } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON: Record<ButtonVariant, string> = {
  primary: "bg-accent text-invert hover:bg-accent-hover",
  secondary: "border border-line-strong bg-raised text-ink hover:bg-hover",
  ghost: "text-accent-ink hover:bg-accent-soft",
  danger: "border border-line text-down hover:bg-down-soft",
};

export function buttonClass(variant: ButtonVariant = "primary", size: "sm" | "md" = "md"): string {
  return cx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm",
    BUTTON[variant],
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("rounded-xl border border-line bg-raised p-5", className)}>{children}</section>;
}

export function CardTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="text-base font-semibold text-ink">{children}</h2>
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-line bg-raised p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={cx("num mt-1 text-xl font-semibold", tone ?? "text-ink")}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

type PillTone = "neutral" | "accent" | "up" | "down" | "warn" | "info";

const PILL: Record<PillTone, string> = {
  neutral: "bg-sub text-muted",
  accent: "bg-accent-soft text-accent-ink",
  up: "bg-up-soft text-up",
  down: "bg-down-soft text-down",
  warn: "bg-warn-soft text-warn",
  info: "bg-info-soft text-info",
};

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: PillTone }) {
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", PILL[tone])}>
      {children}
    </span>
  );
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "up" | "down" | "warn" }) {
  const tones = {
    info: "border-info/30 bg-info-soft text-ink",
    up: "border-up/30 bg-up-soft text-ink",
    down: "border-down/30 bg-down-soft text-ink",
    warn: "border-warn/30 bg-warn-soft text-ink",
  };
  return <div className={cx("rounded-lg border px-4 py-3 text-sm", tones[tone])}>{children}</div>;
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function AffiliateDisclosure() {
  return (
    <p className="text-xs text-faint">
      Some account-opening links are referral links, so BrokerLens may earn a fee if you open an account through
      them. That never changes the fees shown or the order of any ranking, which is sorted by cost alone.
    </p>
  );
}

import type { AnomalyStatus, RiskLevel } from "@/lib/types";
import { Info } from "lucide-react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export const RISK_STYLE: Record<RiskLevel, { badge: string; dot: string; fill: string }> = {
  LOW: { badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500", fill: "#10b981" },
  MEDIUM: { badge: "bg-amber-50 text-amber-800 ring-amber-600/25", dot: "bg-amber-500", fill: "#f59e0b" },
  HIGH: { badge: "bg-orange-50 text-orange-700 ring-orange-600/25", dot: "bg-orange-500", fill: "#f97316" },
  CRITICAL: { badge: "bg-red-50 text-red-700 ring-red-600/25", dot: "bg-red-600", fill: "#dc2626" },
};

export function RiskBadge({ level, score }: { level: RiskLevel; score?: number }) {
  const s = RISK_STYLE[level];
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset", s.badge)}>
      <span className={cx("h-1.5 w-1.5 rounded-full", s.dot)} />
      {level}
      {score !== undefined && <span className="num font-medium opacity-80">· {score.toFixed(0)}</span>}
    </span>
  );
}

const ANOM_STYLE: Record<AnomalyStatus, string> = {
  NORMAL: "bg-slate-50 text-slate-600 ring-slate-500/20",
  WATCH: "bg-violet-50 text-violet-700 ring-violet-600/20",
  ANOMALOUS: "bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-600/25",
};

export function AnomalyBadge({ status }: { status: AnomalyStatus }) {
  return (
    <span className={cx("inline-flex whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", ANOM_STYLE[status])}>
      {status === "NORMAL" ? "Normal" : status === "WATCH" ? "Watch" : "Unusual activity"}
    </span>
  );
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>{children}</div>;
}

export function CardHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-3.5">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Tooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <Info className="h-3.5 w-3.5 text-slate-400" aria-label={text} />
      <span className="pointer-events-none absolute left-1/2 top-5 z-30 hidden w-64 -translate-x-1/2 rounded-md bg-slate-900 px-3 py-2 text-xs font-normal leading-relaxed text-white shadow-lg group-hover:block">
        {text}
      </span>
    </span>
  );
}

export function Kpi({
  label,
  value,
  sub,
  tone = "default",
  tip,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "danger" | "warn" | "good" | "brand";
  tip?: string;
}) {
  const toneCls = {
    default: "text-slate-900",
    danger: "text-red-600",
    warn: "text-orange-600",
    good: "text-emerald-600",
    brand: "text-blue-700",
  }[tone];
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
        {tip && <Tooltip text={tip} />}
      </div>
      <div className={cx("num mt-1.5 text-[22px] font-semibold leading-tight sm:whitespace-nowrap", toneCls)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

export function SourceTag({ kind }: { kind: "model" | "calc" | "rec" | "sim" | "data" }) {
  const map = {
    model: ["ML prediction", "bg-blue-50 text-blue-700 ring-blue-600/20"],
    calc: ["Deterministic calculation", "bg-slate-100 text-slate-700 ring-slate-500/20"],
    rec: ["Recommendation", "bg-teal-50 text-teal-700 ring-teal-600/20"],
    sim: ["Simulation only", "bg-amber-50 text-amber-800 ring-amber-600/25"],
    data: ["Synthetic data", "bg-slate-50 text-slate-600 ring-slate-500/20"],
  } as const;
  const [label, cls] = map[kind];
  return <span className={cx("inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset", cls)}>{label}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 p-8 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-slate-300 bg-white p-6 shadow-sm">
      <p className="text-base font-semibold text-slate-900">Live decision service is temporarily unavailable.</p>
      <p className="mt-1 text-sm text-slate-600">Your data has not changed. Nothing was approved or moved.</p>
      <p className="mt-1 text-xs text-slate-500">Details: {message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          Retry
        </button>
      )}
      <details className="mt-4 text-xs text-slate-500">
        <summary className="cursor-pointer">Running locally?</summary>
        Start the API with <code className="rounded bg-slate-100 px-1.5 py-0.5">uvicorn app.main:app --port 8000</code> from{" "}
        <code>apps/api</code>.
      </details>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function ScoreBar({ value, max = 100, color = "#2563eb" }: { value: number; max?: number; color?: string }) {
  const w = Math.max(0, Math.min(100, (100 * value) / max));
  return (
    <div className="h-1.5 w-full rounded-full bg-slate-100">
      <div className="h-1.5 rounded-full" style={{ width: `${w}%`, backgroundColor: color }} />
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, CheckCircle2, Equal, ShieldAlert, UserCheck, X } from "lucide-react";
import { apiPost, useApi } from "@/lib/api";
import { bdt, bdtCompact, ratioPct, titleCase } from "@/lib/format";
import type {
  MorningPlan,
  MorningPlanAgent,
  MorningPlanDates,
  MorningPlanDistrict,
  MorningPlanEvidence,
  MorningPlanSimulation,
  MorningResource,
  MorningReviewCode,
} from "@/lib/types";
import { MorningEvidencePanel } from "@/components/MorningEvidence";
import { Card, CardHeader, ErrorState, Eyebrow, Loading, PageHeader, RESOURCE_STYLE, ResourceTag, SourceTag, StatusPill, cx } from "@/components/ui";

const TRUST = ["Synthetic demo", "Human-reviewed", "Same working capital", "No money moves"];
const RES: { key: MorningResource; label: string; serves: string }[] = [
  { key: "cash", label: RESOURCE_STYLE.cash.label, serves: RESOURCE_STYLE.cash.serves },
  { key: "efloat", label: RESOURCE_STYLE.efloat.label, serves: RESOURCE_STYLE.efloat.serves },
];
const FLAG_STYLE: Record<string, string> = {
  large_allocation_decrease: "bg-orange-50 text-orange-800 ring-orange-600/25",
  low_volume_review: "bg-violet-50 text-violet-800 ring-violet-600/20",
  rural_efloat_review: "bg-amber-50 text-amber-900 ring-amber-600/25",
  p90_not_covered: "bg-slate-100 text-slate-700 ring-slate-500/20",
};
/** Labels as served by the API (REVIEW_FLAGS in apps/api/app/morning_plan.py). */
const FLAG_LABEL: Record<MorningReviewCode, string> = {
  large_allocation_decrease: "Large allocation decrease",
  low_volume_review: "Low-volume review",
  rural_efloat_review: "Rural e-float review",
  p90_not_covered: "Below full-day P90 need",
};

/** Presentation shortcuts only: they select an existing plan date; they do not change data or defaults. */
const PRESETS = [
  { label: "Normal day", date: "2026-08-24" },
  { label: "Stress day", date: "2026-08-31" },
];

/**
 * District pressure = full-day P90 need ÷ the district's fixed budget, per resource.
 * DISPLAY-ONLY: derived in the browser from this plan's own numbers. It is not a model metric,
 * not stored anywhere, and the bands below are visual categories chosen for readability —
 * they are NOT model, risk or allocator thresholds.
 */
const PRESSURE_BANDS = { coveredBelow: 0.9, tightUpTo: 1.0 };
type PressureState = "Covered" | "Tight" | "Constrained";
function pressureState(ratio: number): PressureState {
  if (ratio < PRESSURE_BANDS.coveredBelow) return "Covered";
  if (ratio <= PRESSURE_BANDS.tightUpTo) return "Tight";
  return "Constrained";
}
const PRESSURE_TONE: Record<PressureState, "safe" | "review" | "critical"> = { Covered: "safe", Tight: "review", Constrained: "critical" };

function dayLabel(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
}
function shortDay(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" });
}

function Delta({ v }: { v: number }) {
  if (v === 0) return <span className="text-slate-400">±0</span>;
  const up = v > 0;
  return (
    <span className={cx("num inline-flex items-center gap-0.5 font-medium", up ? "text-emerald-700" : "text-orange-700")}>
      {up ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />}
      {up ? "+" : "−"}
      {bdt(Math.abs(v)).replace("BDT ", "")}
    </span>
  );
}

function Flags({ a, max = 3 }: { a: MorningPlanAgent; max?: number }) {
  if (!a.review_flags.length) return <span className="text-xs text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {a.review_flags.slice(0, max).map((f) => (
        <span key={f.code} className={cx("whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset", FLAG_STYLE[f.code])}>
          {f.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ date controls */
function DateControls({ dates, current, onPick }: { dates: string[]; current: string | null; onPick: (d: string) => void }) {
  const presets = PRESETS.filter((p) => dates.includes(p.date));
  return (
    <div className="flex flex-wrap items-center gap-2">
      {presets.length > 0 && (
        <div role="group" aria-label="Demo presets" className="inline-flex rounded-lg bg-slate-100 p-0.5">
          {presets.map((p) => (
            <button
              key={p.date}
              onClick={() => onPick(p.date)}
              aria-pressed={current === p.date}
              className={cx(
                "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                current === p.date ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200" : "text-slate-600 hover:text-slate-900",
              )}
            >
              {p.label} <span className="font-normal text-slate-500">· {shortDay(p.date)}</span>
            </button>
          ))}
        </div>
      )}
      <label className="flex items-center gap-2 text-[13px] text-slate-600">
        Plan date
        <select aria-label="Plan date" value={current || ""} onChange={(e) => onPick(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800">
          {dates.map((d) => (
            <option key={d} value={d}>
              {dayLabel(d)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/* ------------------------------------------------------------------ signature: liquidity placement board */
function PlacementRow({ plan, res }: { plan: MorningPlan; res: MorningResource }) {
  const s = plan.network[res];
  const st = RESOURCE_STYLE[res];
  const Icon = st.icon;
  return (
    <div className="grid items-center gap-x-6 gap-y-3 border-t border-white/10 py-4 first:border-t-0 md:grid-cols-[190px_minmax(0,1fr)] xl:grid-cols-[190px_auto_minmax(0,1fr)]">
      <div className="flex items-center gap-3">
        <span className={cx("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", res === "cash" ? "bg-cash-600/25 text-cash-300" : "bg-efloat-600/25 text-efloat-300")}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div>
          <div className="text-base font-semibold text-white">{st.label}</div>
          <div className={cx("text-[13px]", st.darkText)}>{st.serves}</div>
        </div>
      </div>
      <div className="flex flex-wrap items-end gap-x-5 gap-y-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">Current</div>
          <div className="num text-[28px] font-semibold leading-none tracking-tight text-slate-100">{bdtCompact(s.status_quo_total_bdt)}</div>
          <div className="num mt-1 text-xs text-slate-400">{bdt(s.status_quo_total_bdt)}</div>
        </div>
        <ArrowRight className="mb-5 h-6 w-6 shrink-0 text-slate-500" aria-label="becomes" />
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-blue-300">AgentFlow plan</div>
          <div className="num text-[28px] font-semibold leading-none tracking-tight text-white">{bdtCompact(s.recommended_total_bdt)}</div>
          <div className="mt-1 flex items-center gap-1 text-xs text-emerald-300">
            {s.difference_bdt === 0 ? (
              <>
                <Equal className="h-3.5 w-3.5" aria-hidden /> matches budget exactly
              </>
            ) : (
              <span className="text-red-300">MISMATCH</span>
            )}
          </div>
        </div>
      </div>
      <dl className="grid max-w-[340px] grid-cols-2 gap-x-4 gap-y-2 text-[13px] md:col-span-2 xl:col-span-1 xl:border-l xl:border-white/10 xl:pl-6">
        <div>
          <dt className="text-slate-400">Repositioned</dt>
          <dd className="num font-semibold text-slate-100">{bdtCompact(s.repositioned_bdt)}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Agents up / down</dt>
          <dd className="num font-semibold">
            <span className="text-emerald-300">↑{s.agents_increased}</span> <span className="text-slate-500">/</span>{" "}
            <span className="text-orange-300">↓{s.agents_decreased}</span>
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Full-day P90 need</dt>
          <dd className="num font-semibold text-slate-100">{bdtCompact(s.p90_need_total_bdt)}</dd>
        </div>
        <div>
          <dt className="text-slate-400">P90 need covered</dt>
          <dd className="num font-semibold text-slate-100">
            {s.agents_p90_covered_before} → <span className="text-white">{s.agents_p90_covered_after}</span>
            <span className="font-normal text-slate-400"> of {plan.network.agents}</span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

function PlacementBoard({ plan, stress }: { plan: MorningPlan; stress: boolean }) {
  const n = plan.network;
  return (
    <section aria-labelledby="placement-title" className="surface-navy af-rise mb-5 overflow-hidden rounded-2xl border border-navy-700 shadow-[0_10px_30px_-18px_rgba(7,16,31,0.7)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-6 py-3.5">
        <div>
          <Eyebrow className="text-blue-300">
            <span id="placement-title">Liquidity placement board</span>
          </Eyebrow>
          <p className="mt-0.5 text-[13px] text-slate-300">
            Plan for <b className="text-white">{dayLabel(plan.date)}</b> · horizon {plan.meta.horizon} · {n.agents} agents · frozen full-day P90 forecast
            {stress && <span className="ml-2 rounded bg-amber-400/15 px-1.5 py-0.5 text-[11px] font-semibold text-amber-200">Stress-day example — not an average day</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-semibold" aria-label="Morning plan timeline">
          <span className="rounded-md bg-blue-500/90 px-2.5 py-1 text-white">07:00 Predict</span>
          <ArrowRight className="h-4 w-4 text-slate-500" aria-hidden />
          <span className="rounded-md bg-blue-500/90 px-2.5 py-1 text-white">08:00 Position</span>
          <ArrowRight className="h-4 w-4 text-slate-500" aria-hidden />
          <span className="rounded-md bg-white/[0.08] px-2.5 py-1 text-slate-200 ring-1 ring-inset ring-white/10">Intraday monitor (6-hour risk + V2)</span>
        </div>
      </div>
      <div className="px-6 py-1">
        <PlacementRow plan={plan} res="cash" />
        <PlacementRow plan={plan} res="efloat" />
      </div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-white/10 bg-white/[0.03] px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="num text-[40px] font-semibold leading-none tracking-tight text-white">BDT {n.extra_working_capital_bdt}</div>
          <div>
            <div className="text-[13px] font-semibold uppercase tracking-[0.12em] text-slate-300">extra working capital</div>
            <div
              className={cx(
                "mt-1 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                n.conserved ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-400/30" : "bg-red-500/20 text-red-200",
              )}
            >
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
              {n.conserved ? "Every district conserved exactly" : "Conservation check failed"}
            </div>
          </div>
        </div>
        <div className="ml-auto max-w-xl text-right">
          <p className="text-xl font-semibold tracking-tight text-white">Same amount. Different placement.</p>
          <p className="text-[13px] text-slate-400">
            Cash and e-float budgets are conserved <b className="text-slate-200">separately</b> in every district — the plan never converts one into the other.
          </p>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ district pressure (display-only) */
function PressureBar({ ratio, res }: { ratio: number; res: MorningResource }) {
  const scaleMax = 1.25;
  const w = Math.min(ratio / scaleMax, 1) * 100;
  const budgetAt = (1 / scaleMax) * 100;
  return (
    <div className="relative h-2 rounded-full bg-slate-100" aria-hidden>
      <div className={cx("af-bar absolute h-2 rounded-full", RESOURCE_STYLE[res].bar)} style={{ width: `${w}%` }} />
      <div className="absolute -top-1 h-4 w-px bg-slate-500" style={{ left: `${budgetAt}%` }} />
    </div>
  );
}

function DistrictPressure({ plan }: { plan: MorningPlan }) {
  const rows = useMemo(
    () =>
      plan.districts
        .map((d: MorningPlanDistrict) => ({
          d,
          cash: d.cash_budget_bdt > 0 ? d.cash_p90_need_bdt / d.cash_budget_bdt : 0,
          efloat: d.efloat_budget_bdt > 0 ? d.efloat_p90_need_bdt / d.efloat_budget_bdt : 0,
        }))
        .sort((a, b) => Math.max(b.cash, b.efloat) - Math.max(a.cash, a.efloat)),
    [plan],
  );
  const constrained = rows.filter((r) => r.cash > PRESSURE_BANDS.tightUpTo || r.efloat > PRESSURE_BANDS.tightUpTo).length;
  return (
    <Card className="mb-5">
      <CardHeader
        title="District pressure — P90 need / available district budget"
        subtitle="Display-only indicator computed from this plan's numbers; not a model metric. When need approaches or exceeds a fixed budget, not every agent can be fully covered — AgentFlow must choose where the same liquidity should sit."
        right={<SourceTag kind="calc" />}
      />
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-2.5 text-xs text-slate-600">
        <span className="font-medium text-slate-700">Bands (visual only):</span>
        <StatusPill tone="safe">Covered &lt; {PRESSURE_BANDS.coveredBelow.toFixed(2)}×</StatusPill>
        <StatusPill tone="review">
          Tight {PRESSURE_BANDS.coveredBelow.toFixed(2)}–{PRESSURE_BANDS.tightUpTo.toFixed(2)}×
        </StatusPill>
        <StatusPill tone="critical">Constrained &gt; {PRESSURE_BANDS.tightUpTo.toFixed(2)}×</StatusPill>
        <span className="ml-auto text-slate-500">
          Tick mark = district budget (1.00×) · {constrained} of {rows.length} districts constrained on this date
        </span>
      </div>
      <div className="grid gap-px bg-slate-100 sm:grid-cols-2 xl:grid-cols-4">
        {rows.map(({ d, cash, efloat }) => (
          <div key={d.district} className="bg-white px-4 py-3">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-[15px] font-semibold text-slate-900">{d.district}</span>
              <span className="text-xs text-slate-500">{d.agents} agents</span>
            </div>
            {(["cash", "efloat"] as MorningResource[]).map((r) => {
              const ratio = r === "cash" ? cash : efloat;
              const state = pressureState(ratio);
              return (
                <div key={r} className="mb-2 last:mb-0">
                  <div className="mb-1 flex items-center justify-between gap-2 text-[13px]">
                    <span className={cx("font-medium", RESOURCE_STYLE[r].text)}>{r === "cash" ? "Cash" : "E-float"}</span>
                    <span className="flex items-center gap-1.5">
                      <span className="num font-semibold text-slate-900">{ratio.toFixed(2)}×</span>
                      <StatusPill tone={PRESSURE_TONE[state]}>{state}</StatusPill>
                    </span>
                  </div>
                  <PressureBar ratio={ratio} res={r} />
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ review focus */
function ReviewFocus({ plan, onOpen }: { plan: MorningPlan; onOpen: (id: string) => void }) {
  const f = plan.review_focus;
  const counts = plan.network.flag_counts;
  const maxCut = Math.max(1, ...f.largest_cuts.map((a) => Math.max(-a.cash_delta, -a.efloat_delta, 0)));
  const row = (a: (typeof f.largest_cuts)[number], i: number, res?: MorningResource, bar = false) => {
    const cut = Math.max(-a.cash_delta, -a.efloat_delta, 0);
    return (
      <li key={a.agent_id + (res || "")}>
        <button onClick={() => onOpen(a.agent_id)} className="w-full rounded-md px-2 py-1.5 text-left transition-colors hover:bg-slate-50">
          <div className="flex items-center justify-between gap-2 text-[13px]">
            <span className="flex min-w-0 items-center gap-2">
              <span className="num w-4 shrink-0 text-right text-xs text-slate-400">{i + 1}</span>
              <span className="min-w-0">
                <span className="whitespace-nowrap font-semibold text-blue-700">{a.agent_id}</span>
                <span className="block truncate text-xs text-slate-500">
                  {a.district} · {titleCase(a.location_cluster)} · {a.agent_volume_segment}
                </span>
              </span>
            </span>
            <span className="flex shrink-0 flex-col items-end text-xs">
              {(!res || res === "cash") && (
                <span className="whitespace-nowrap">
                  <span className={RESOURCE_STYLE.cash.text}>cash</span> <Delta v={a.cash_delta} />
                </span>
              )}
              {(!res || res === "efloat") && (
                <span className="whitespace-nowrap">
                  <span className={RESOURCE_STYLE.efloat.text}>e-float</span> <Delta v={a.efloat_delta} />
                </span>
              )}
            </span>
          </div>
          {bar && (
            <div className="ml-6 mt-1 h-1 rounded-full bg-slate-100" aria-hidden>
              <div className="af-bar h-1 rounded-full bg-orange-400" style={{ width: `${(100 * cut) / maxCut}%` }} />
            </div>
          )}
        </button>
      </li>
    );
  };
  return (
    <Card className="mb-5 border-amber-200">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-t-xl border-b border-amber-100 bg-amber-50/60 px-5 py-3.5">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-700" aria-hidden />
          <div>
            <h3 className="text-[15px] font-semibold text-amber-950">Human attention required</h3>
            <p className="text-[13px] text-amber-900/80">Review focus · difficult recommendations a person should check first, largest cuts first.</p>
          </div>
        </div>
        <ul className="flex flex-wrap gap-1.5" aria-label="Review flags on this date">
          {(Object.keys(FLAG_LABEL) as MorningReviewCode[]).map((code) => (
            <li key={code} className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ring-1 ring-inset", FLAG_STYLE[code])}>
              {FLAG_LABEL[code]} <span className="num rounded bg-white/70 px-1">{counts[code] ?? 0}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="p-5">
        <div className={cx("mb-4 flex items-center gap-2 rounded-md px-3 py-2 text-[13px] font-medium", f.conserved ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800")}>
          <CheckCircle2 className="h-4 w-4" aria-hidden />
          {f.conserved ? "Conservation: every district's cash and e-float total is unchanged." : "Conservation check failed — do not use this plan."}
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          <section className="min-w-0">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Largest allocation cuts</h4>
            <ul className="mt-1.5 space-y-0.5">{f.largest_cuts.map((a, i) => row(a, i, undefined, true))}</ul>
          </section>
          <section className="min-w-0">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Low-volume agents receiving cuts ({f.low_volume_cuts_total})</h4>
            {f.low_volume_cuts.length ? <ul className="mt-1.5 space-y-0.5">{f.low_volume_cuts.map((a, i) => row(a, i))}</ul> : <p className="mt-1.5 text-[13px] text-slate-400">None on this date.</p>}
          </section>
          <section className="min-w-0">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Rural agents with large e-float reductions ({f.rural_efloat_cuts_total})</h4>
            {f.rural_efloat_cuts.length ? (
              <ul className="mt-1.5 space-y-0.5">{f.rural_efloat_cuts.map((a, i) => row(a, i, "efloat"))}</ul>
            ) : (
              <p className="mt-1.5 text-[13px] text-slate-400">None on this date.</p>
            )}
          </section>
        </div>
        <p className="mt-4 text-xs leading-snug text-slate-500">
          Review indicators describe the plan itself. Future outcomes are unknown at 07:00; in historical synthetic research, low-volume agents did worse
          than a cautious q90 rule in 4 of 5 audit worlds.
        </p>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ agent table */
type SortKey = "agent_id" | "cash_delta" | "efloat_delta" | "p90";
type Filter = "all" | "flagged" | "cash_down" | "efloat_down";

function AgentTable({ plan, onOpen }: { plan: MorningPlan; onOpen: (id: string) => void }) {
  const [sort, setSort] = useState<SortKey>("cash_delta");
  const [asc, setAsc] = useState(true);
  const [filter, setFilter] = useState<Filter>("flagged");
  const rows = useMemo(() => {
    const f = plan.agents.filter((a) =>
      filter === "all" ? true : filter === "flagged" ? a.review_flags.length > 0 : filter === "cash_down" ? a.cash_delta < 0 : a.efloat_delta < 0,
    );
    const val = (a: MorningPlanAgent) => (sort === "agent_id" ? a.agent_id : sort === "p90" ? a.cash_p90 + a.efloat_p90 : a[sort]);
    return [...f].sort((x, y) => {
      const a = val(x), b = val(y);
      const c = typeof a === "string" ? a.localeCompare(b as string) : (a as number) - (b as number);
      return asc ? c : -c;
    });
  }, [plan, sort, asc, filter]);
  const th = (key: SortKey, label: React.ReactNode, right = false) => (
    <th className={cx("px-3 py-2 font-medium", right && "text-right")} aria-sort={sort === key ? (asc ? "ascending" : "descending") : "none"}>
      <button className="hover:text-slate-900" onClick={() => (sort === key ? setAsc(!asc) : (setSort(key), setAsc(key === "agent_id")))}>
        {label}
        {sort === key ? (asc ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  return (
    <Card className="mb-5">
      <CardHeader
        title="Agent plan"
        subtitle="Current morning allocation → recommended. Click an agent for the full explanation."
        right={
          <select aria-label="Filter agents" value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[13px]">
            <option value="flagged">Review flagged ({plan.agents.filter((a) => a.review_flags.length).length})</option>
            <option value="all">All agents ({plan.agents.length})</option>
            <option value="cash_down">Cash decreased ({plan.network.cash.agents_decreased})</option>
            <option value="efloat_down">E-float decreased ({plan.network.efloat.agents_decreased})</option>
          </select>
        }
      />
      <div className="max-h-[460px] overflow-auto">
        <table className="w-full whitespace-nowrap text-xs">
          <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              {th("agent_id", "Agent")}
              <th className="px-3 py-2 font-medium">District · group</th>
              {th("cash_delta", <span className={RESOURCE_STYLE.cash.text}>Cash: now → plan</span>, true)}
              {th("efloat_delta", <span className={RESOURCE_STYLE.efloat.text}>E-float: now → plan</span>, true)}
              {th("p90", "P90 need cash / e-float", true)}
              <th className="px-3 py-2 font-medium">Review status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  No agents match this filter on this date.
                </td>
              </tr>
            )}
            {rows.map((a) => (
              <tr key={a.agent_id} className="cursor-pointer transition-colors hover:bg-blue-50/40" onClick={() => onOpen(a.agent_id)}>
                <td className="px-3 py-2">
                  <button
                    className="font-medium text-blue-700 hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(a.agent_id);
                    }}
                  >
                    {a.agent_id}
                  </button>
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {a.district}
                  <span className="block text-xs text-slate-400">
                    {titleCase(a.location_cluster)} · {a.agent_volume_segment}
                  </span>
                </td>
                <td className="num px-3 py-2 text-right">
                  {bdt(a.status_quo_cash).replace("BDT ", "")} → <b>{bdt(a.recommended_cash).replace("BDT ", "")}</b> <Delta v={a.cash_delta} />
                </td>
                <td className="num px-3 py-2 text-right">
                  {bdt(a.status_quo_efloat).replace("BDT ", "")} → <b>{bdt(a.recommended_efloat).replace("BDT ", "")}</b> <Delta v={a.efloat_delta} />
                </td>
                <td className="num px-3 py-2 text-right text-slate-600">
                  {bdt(a.cash_p90).replace("BDT ", "")} / {bdt(a.efloat_p90).replace("BDT ", "")}
                </td>
                <td className="min-w-[150px] whitespace-normal px-3 py-2">
                  <Flags a={a} max={2} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function DistrictTable({ plan }: { plan: MorningPlan }) {
  return (
    <Card className="mb-5">
      <CardHeader title="District budgets — conservation proof" subtitle="Each district keeps exactly its status-quo cash and e-float; only the split between agents changes." right={<SourceTag kind="calc" />} />
      <div className="overflow-x-auto">
        <table className="w-full whitespace-nowrap text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">District</th>
              <th className={cx("px-3 py-2 text-right font-medium", RESOURCE_STYLE.cash.text)}>Cash budget</th>
              <th className={cx("px-3 py-2 text-right font-medium", RESOURCE_STYLE.cash.text)}>Recommended cash</th>
              <th className={cx("px-3 py-2 text-right font-medium", RESOURCE_STYLE.efloat.text)}>E-float budget</th>
              <th className={cx("px-3 py-2 text-right font-medium", RESOURCE_STYLE.efloat.text)}>Recommended e-float</th>
              <th className="px-3 py-2 text-right font-medium">Agents changed ≥ BDT 5,000</th>
              <th className="px-3 py-2 font-medium">Conserved</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {plan.districts.map((d) => (
              <tr key={d.district}>
                <td className="px-3 py-2">{d.district}</td>
                <td className="num px-3 py-2 text-right">{bdt(d.cash_budget_bdt)}</td>
                <td className="num px-3 py-2 text-right">{bdt(d.cash_recommended_bdt)}</td>
                <td className="num px-3 py-2 text-right">{bdt(d.efloat_budget_bdt)}</td>
                <td className="num px-3 py-2 text-right">{bdt(d.efloat_recommended_bdt)}</td>
                <td className="num px-3 py-2 text-right">
                  {d.agents_with_meaningful_change} / {d.agents}
                </td>
                <td className="px-3 py-2">
                  {d.conserved ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                      BDT 0 difference
                    </span>
                  ) : (
                    <span className="text-xs font-semibold text-red-700">mismatch</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
        {plan.network.matches_frozen_demo_fixture_allocation
          ? "Live allocation matches the frozen serving fixture exactly. The compact fixture differs from the original unrounded research allocation by at most BDT 1 due to forecast rounding."
          : "Live allocation does not match the frozen serving fixture — do not use this plan."}
      </p>
    </Card>
  );
}

/* ------------------------------------------------------------------ explanation drawer */
function AgentDrawer({ a, onClose }: { a: MorningPlanAgent; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="af-backdrop fixed inset-0 z-40 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Morning plan explanation for ${a.agent_id}`}
        className="af-drawer h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-2xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{a.agent_id}</h2>
            <p className="text-[13px] text-slate-500">
              {a.district} · {titleCase(a.location_cluster)} · {a.agent_volume_segment} volume
            </p>
          </div>
          <button onClick={onClose} aria-label="Close explanation" className="rounded p-1 text-slate-500 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mb-3">
          <Flags a={a} max={4} />
        </div>
        {RES.map(({ key }) => (
          <section key={key} className={cx("mb-3 rounded-lg border p-3", key === "cash" ? "border-cash-100" : "border-efloat-100")}>
            <div className="mb-2">
              <ResourceTag res={key} withServes />
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[13px]">
              <dt className="text-slate-500">Current morning allocation</dt>
              <dd className="num text-right">{bdt(a[`status_quo_${key}`])}</dd>
              <dt className="text-slate-500">Predicted full-day P50</dt>
              <dd className="num text-right">{bdt(a[`${key}_p50`])}</dd>
              <dt className="text-slate-500">Predicted full-day P90</dt>
              <dd className="num text-right">{bdt(a[`${key}_p90`])}</dd>
              <dt className="text-slate-500">Recommended allocation</dt>
              <dd className="num text-right font-semibold">{bdt(a[`recommended_${key}`])}</dd>
              <dt className="text-slate-500">Change</dt>
              <dd className="text-right">
                <Delta v={a[`${key}_delta`]} />
              </dd>
              <dt className="text-slate-500">P90 coverage before → after</dt>
              <dd className="num text-right">
                {ratioPct(a[`${key}_coverage_before`])} → {ratioPct(a[`${key}_coverage_after`])}
              </dd>
            </dl>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-700">{a.explanation[key]}</p>
          </section>
        ))}
        <section className="mb-3 rounded-lg border border-slate-200 p-3 text-[13px] leading-relaxed text-slate-700">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Why this plan</h3>
          {a.explanation.constraint}
        </section>
        <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-[13px] leading-relaxed text-amber-950">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide">Safety</h3>
          {a.explanation.safety} Explanations come from fixed templates over the plan&apos;s numbers — not from a language model and not from per-agent causal
          attribution.
        </section>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ approval */
function Approval({ plan }: { plan: MorningPlan }) {
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<MorningPlanSimulation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setRes(null);
    setAck(false);
    setErr(null);
  }, [plan.date]);
  const approve = async () => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await apiPost<MorningPlanSimulation>("/api/morning-plan/simulate", { date: plan.date, reviewer_acknowledged: true, reviewer_note: "Morning Plan review (demo)" }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mb-5 border-slate-300">
      <CardHeader title="Human review" subtitle="Approving runs a simulation and writes an audit entry. Nothing is transferred." right={<SourceTag kind="sim" />} />
      <div className="flex flex-wrap items-center gap-3 p-4 text-sm">
        {res ? (
          <div role="status" className="af-confirm flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-emerald-900 ring-1 ring-emerald-200">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            <b>{res.status}</b>
            <span className="text-[13px]">
              {res.simulation_id} · cash {bdt(res.conservation.network.cash.status_quo_total_bdt)} → {bdt(res.conservation.network.cash.recommended_total_bdt)} · e-float{" "}
              {bdt(res.conservation.network.efloat.status_quo_total_bdt)} → {bdt(res.conservation.network.efloat.recommended_total_bdt)} · extra working capital BDT{" "}
              {res.conservation.extra_working_capital_bdt}
            </span>
          </div>
        ) : (
          <>
            <UserCheck className="h-5 w-5 text-slate-500" aria-hidden />
            <label className="flex items-center gap-2 text-[13px] text-slate-700">
              <input type="checkbox" className="h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              I have reviewed the plan, including the review-focus agents.
            </label>
            <button
              onClick={approve}
              disabled={!ack || busy}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Simulating…" : "Approve Simulation"}
            </button>
            {err && <span className="text-[13px] text-red-700">{err}</span>}
          </>
        )}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ page */
export default function MorningPlanPage() {
  const dates = useApi<MorningPlanDates>("/api/morning-plan/dates");
  const [date, setDate] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const current = date || dates.data?.default_date || null;
  const plan = useApi<MorningPlan>(current ? "/api/morning-plan" : null, { date: current });
  const ev = useApi<MorningPlanEvidence>("/api/morning-plan/evidence");
  const agent = plan.data?.agents.find((a) => a.agent_id === open) || null;
  const stress = !!plan.data && plan.data.date === PRESETS[1].date;

  return (
    <>
      <PageHeader
        eyebrow="Morning · proactive full-day plan"
        title="Morning Liquidity Plan"
        subtitle="Pre-position physical cash and e-float before demand arrives — using the same working capital."
        right={
          dates.data && (
            <DateControls
              dates={dates.data.dates}
              current={current}
              onPick={(d) => {
                setDate(d);
                setOpen(null);
              }}
            />
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-1.5" aria-label="Trust labels">
        {TRUST.map((t) => (
          <span key={t} className="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">
            {t}
          </span>
        ))}
        <span className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600 ring-1 ring-inset ring-slate-200">Proactive full-day plan · intraday V2 stays reactive</span>
        <span className="ml-auto text-xs text-slate-500">Presets are shortcuts; the stress day is an illustrative example, not an average day.</span>
      </div>

      {dates.error && <ErrorState message={dates.error} onRetry={dates.reload} />}
      {plan.error && <ErrorState message={plan.error} onRetry={plan.reload} />}
      {!plan.data && !plan.error && !dates.error && <Loading label="Loading the Morning Plan…" />}
      {dates.data && dates.data.dates.length === 0 && <p className="text-sm text-slate-500">No Morning Plan dates are available.</p>}

      {plan.data && (
        <div className={plan.loading ? "opacity-60 transition-opacity" : ""}>
          <PlacementBoard plan={plan.data} stress={stress} />
          <DistrictPressure plan={plan.data} />
          <ReviewFocus plan={plan.data} onOpen={setOpen} />
          <Approval plan={plan.data} />
          <AgentTable plan={plan.data} onOpen={setOpen} />
          <DistrictTable plan={plan.data} />
          <p className="mb-6 text-xs text-slate-500">
            {plan.data.meta.labels.synthetic}. Demo fixture: synthetic seed {plan.data.meta.demo_seed}; frozen model spec {plan.data.meta.frozen_model_spec_commit.slice(0, 7)}.
            Allocation recomputed live; no performance claim is made for this date.
          </p>
        </div>
      )}
      {ev.data && <MorningEvidencePanel ev={ev.data} />}
      {ev.error && !plan.error && <ErrorState message={ev.error} onRetry={ev.reload} />}
      {agent && <AgentDrawer a={agent} onClose={() => setOpen(null)} />}
    </>
  );
}

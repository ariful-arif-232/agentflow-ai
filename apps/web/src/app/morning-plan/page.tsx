"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, CheckCircle2, ShieldCheck, X } from "lucide-react";
import { apiPost, useApi } from "@/lib/api";
import { bdt, bdtCompact, ratioPct, titleCase } from "@/lib/format";
import type { MorningPlan, MorningPlanAgent, MorningPlanDates, MorningPlanEvidence, MorningPlanSimulation, MorningResource } from "@/lib/types";
import { MorningEvidencePanel } from "@/components/MorningEvidence";
import { Card, CardHeader, ErrorState, Loading, PageHeader, SourceTag, cx } from "@/components/ui";

const TRUST = ["Synthetic demo", "Human-reviewed", "Same working capital", "No money moves"];
const RES: { key: MorningResource; label: string; serves: string }[] = [
  { key: "cash", label: "Physical cash", serves: "serves cash-out" },
  { key: "efloat", label: "E-float", serves: "serves cash-in" },
];
const FLAG_STYLE: Record<string, string> = {
  large_allocation_decrease: "bg-orange-50 text-orange-800 ring-orange-600/25",
  low_volume_review: "bg-violet-50 text-violet-800 ring-violet-600/20",
  rural_efloat_review: "bg-amber-50 text-amber-900 ring-amber-600/25",
  p90_not_covered: "bg-slate-100 text-slate-700 ring-slate-500/20",
};

function dayLabel(d: string) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
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
        <span key={f.code} className={cx("whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset", FLAG_STYLE[f.code])}>
          {f.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ hero */
function Hero({ plan }: { plan: MorningPlan }) {
  const n = plan.network;
  const tile = (label: string, value: number, sub: string, tone = "text-slate-900") => (
    <div className="rounded-lg border border-slate-200 bg-white px-3.5 py-2.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("num mt-0.5 text-lg font-semibold", tone)}>{bdtCompact(value)}</div>
      <div className="text-[11px] text-slate-500">{sub}</div>
    </div>
  );
  return (
    <Card className="mb-4 border-blue-200 bg-gradient-to-r from-blue-50/80 to-white">
      <div className="grid gap-4 p-4 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900" aria-label="Morning plan timeline">
            <span className="rounded-md bg-blue-700 px-2 py-0.5 text-white">07:00 Predict</span>
            <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden />
            <span className="rounded-md bg-blue-700 px-2 py-0.5 text-white">08:00 Position</span>
            <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden />
            <span className="rounded-md bg-white px-2 py-0.5 text-blue-800 ring-1 ring-inset ring-blue-200">Intraday monitor (6-hour risk + V2)</span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            Plan for <b>{dayLabel(plan.date)}</b> · full-day horizon {plan.meta.horizon} · {plan.network.agents} agents · signal:{" "}
            frozen full-day P90 forecast.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            {tile("Cash budget", n.cash.status_quo_total_bdt, "status-quo morning total")}
            {tile("Recommended cash", n.cash.recommended_total_bdt, n.cash.difference_bdt === 0 ? "matches budget exactly" : "MISMATCH", "text-blue-700")}
            {tile("E-float budget", n.efloat.status_quo_total_bdt, "status-quo morning total")}
            {tile("Recommended e-float", n.efloat.recommended_total_bdt, n.efloat.difference_bdt === 0 ? "matches budget exactly" : "MISMATCH", "text-blue-700")}
          </div>
        </div>
        <div className="rounded-xl bg-[#0b1220] px-5 py-4 text-center text-white">
          <div className="num text-2xl font-bold">BDT {n.extra_working_capital_bdt}</div>
          <div className="text-xs text-slate-300">extra working capital</div>
          <div className={cx("mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold", n.conserved ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300")}>
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
            {n.conserved ? "Every district conserved exactly" : "Conservation check failed"}
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ resource plan */
function ResourcePlan({ plan }: { plan: MorningPlan }) {
  return (
    <div className="mb-4 grid gap-4 lg:grid-cols-2">
      {RES.map(({ key, label, serves }) => {
        const s = plan.network[key];
        return (
          <Card key={key}>
            <CardHeader title={`${label} plan`} subtitle={`${serves.charAt(0).toUpperCase() + serves.slice(1)} · same total, repositioned by full-day P90 need`} right={<SourceTag kind="rec" />} />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 p-4 text-sm sm:grid-cols-3">
              <div><dt className="text-xs text-slate-500">Budget (unchanged)</dt><dd className="num font-semibold">{bdtCompact(s.recommended_total_bdt)}</dd></div>
              <div><dt className="text-xs text-slate-500">Repositioned</dt><dd className="num font-semibold">{bdtCompact(s.repositioned_bdt)}</dd></div>
              <div><dt className="text-xs text-slate-500">Full-day P90 need</dt><dd className="num font-semibold">{bdtCompact(s.p90_need_total_bdt)}</dd></div>
              <div><dt className="text-xs text-slate-500">Agents increased / decreased</dt><dd className="num font-semibold"><span className="text-emerald-700">{s.agents_increased}</span> / <span className="text-orange-700">{s.agents_decreased}</span></dd></div>
              <div className="col-span-2"><dt className="text-xs text-slate-500">Agents whose P90 need is covered</dt><dd className="num font-semibold">{s.agents_p90_covered_before} → <span className="text-blue-700">{s.agents_p90_covered_after}</span> of {plan.network.agents}</dd></div>
            </dl>
          </Card>
        );
      })}
    </div>
  );
}

function DistrictTable({ plan }: { plan: MorningPlan }) {
  return (
    <Card className="mb-4">
      <CardHeader title="District budgets — conservation proof" subtitle="Each district keeps exactly its status-quo cash and e-float; only the split between agents changes." right={<SourceTag kind="calc" />} />
      <div className="overflow-x-auto">
        <table className="w-full whitespace-nowrap text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">District</th>
              <th className="px-4 py-2 text-right font-medium">Cash budget</th>
              <th className="px-4 py-2 text-right font-medium">Recommended cash</th>
              <th className="px-4 py-2 text-right font-medium">E-float budget</th>
              <th className="px-4 py-2 text-right font-medium">Recommended e-float</th>
              <th className="px-4 py-2 text-right font-medium">Agents changed ≥ BDT 5,000</th>
              <th className="px-4 py-2 font-medium">Conserved</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {plan.districts.map((d) => (
              <tr key={d.district}>
                <td className="px-4 py-2">{d.district}</td>
                <td className="num px-4 py-2 text-right">{bdt(d.cash_budget_bdt)}</td>
                <td className="num px-4 py-2 text-right">{bdt(d.cash_recommended_bdt)}</td>
                <td className="num px-4 py-2 text-right">{bdt(d.efloat_budget_bdt)}</td>
                <td className="num px-4 py-2 text-right">{bdt(d.efloat_recommended_bdt)}</td>
                <td className="num px-4 py-2 text-right">{d.agents_with_meaningful_change} / {d.agents}</td>
                <td className="px-4 py-2">
                  {d.conserved ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden />BDT 0 difference</span>
                  ) : (
                    <span className="text-xs font-semibold text-red-700">mismatch</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        {plan.network.matches_frozen_demo_fixture_allocation
          ? "Live allocation matches the frozen serving fixture exactly. The compact fixture differs from the original unrounded research allocation by at most BDT 1 due to forecast rounding."
          : "Live allocation does not match the frozen serving fixture — do not use this plan."}
      </p>
    </Card>
  );
}

/* ------------------------------------------------------------------ review focus */
function ReviewFocus({ plan, onOpen }: { plan: MorningPlan; onOpen: (id: string) => void }) {
  const f = plan.review_focus;
  const row = (a: (typeof f.largest_cuts)[number], res?: MorningResource) => (
    <li key={a.agent_id + (res || "")}>
      <button onClick={() => onOpen(a.agent_id)} className="flex w-full items-center justify-between gap-2 rounded px-1 py-1 text-left text-xs hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
        <span className="min-w-0">
          <span className="whitespace-nowrap font-medium text-blue-700">{a.agent_id}</span>
          <span className="block truncate text-[11px] text-slate-500">{a.district} · {titleCase(a.location_cluster)} · {a.agent_volume_segment}</span>
        </span>
        <span className="flex shrink-0 flex-col items-end">
          {(!res || res === "cash") && <span className="whitespace-nowrap">cash <Delta v={a.cash_delta} /></span>}
          {(!res || res === "efloat") && <span className="whitespace-nowrap">e-float <Delta v={a.efloat_delta} /></span>}
        </span>
      </button>
    </li>
  );
  return (
    <Card className="mb-4">
      <CardHeader title="Review focus" subtitle="Difficult recommendations a person should check first" right={<ShieldCheck className="h-4 w-4 text-slate-400" aria-hidden />} />
      <div className="p-4">
        <div className={cx("mb-3 rounded-md px-2.5 py-1.5 text-xs font-semibold", f.conserved ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800")}>
          {f.conserved ? "Conservation: every district's cash and e-float total is unchanged." : "Conservation check failed — do not use this plan."}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Largest allocation cuts</h4>
          <ul className="mt-1 space-y-0.5">{f.largest_cuts.map((a) => row(a))}</ul>
        </section>
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Low-volume agents receiving cuts ({f.low_volume_cuts_total})</h4>
          {f.low_volume_cuts.length ? <ul className="mt-1 space-y-0.5">{f.low_volume_cuts.map((a) => row(a))}</ul> : <p className="mt-1 text-xs text-slate-400">None on this date.</p>}
        </section>
        <section>
          <h4 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Rural agents with large e-float reductions ({f.rural_efloat_cuts_total})</h4>
          {f.rural_efloat_cuts.length ? <ul className="mt-1 space-y-0.5">{f.rural_efloat_cuts.map((a) => row(a, "efloat"))}</ul> : <p className="mt-1 text-xs text-slate-400">None on this date.</p>}
        </section>
        </div>
        <p className="mt-3 text-[11px] leading-snug text-slate-500">
          Review indicators describe the plan itself. Future outcomes are unknown at 07:00; in historical synthetic research,
          low-volume agents did worse than a cautious q90 rule in 4 of 5 audit worlds.
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
  const th = (key: SortKey, label: string, right = false) => (
    <th className={cx("px-3 py-2 font-medium", right && "text-right")} aria-sort={sort === key ? (asc ? "ascending" : "descending") : "none"}>
      <button className="hover:text-slate-900" onClick={() => (sort === key ? setAsc(!asc) : (setSort(key), setAsc(key === "agent_id")))}>
        {label}{sort === key ? (asc ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  return (
    <Card className="mb-4">
      <CardHeader
        title="Agent plan"
        subtitle="Current morning allocation → recommended. Click an agent for the full explanation."
        right={
          <select aria-label="Filter agents" value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs">
            <option value="flagged">Review flagged ({plan.agents.filter((a) => a.review_flags.length).length})</option>
            <option value="all">All agents ({plan.agents.length})</option>
            <option value="cash_down">Cash decreased ({plan.network.cash.agents_decreased})</option>
            <option value="efloat_down">E-float decreased ({plan.network.efloat.agents_decreased})</option>
          </select>
        }
      />
      <div className="max-h-[460px] overflow-auto">
        <table className="w-full whitespace-nowrap text-xs">
          <thead className="sticky top-0 z-10 bg-slate-50 text-left text-slate-500">
            <tr>
              {th("agent_id", "Agent")}
              <th className="px-3 py-2 font-medium">District · group</th>
              {th("cash_delta", "Cash: now → plan", true)}
              {th("efloat_delta", "E-float: now → plan", true)}
              {th("p90", "P90 need cash / e-float", true)}
              <th className="px-3 py-2 font-medium">Review status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500">No agents match this filter on this date.</td></tr>
            )}
            {rows.map((a) => (
              <tr key={a.agent_id} className="cursor-pointer hover:bg-blue-50/40" onClick={() => onOpen(a.agent_id)}>
                <td className="px-3 py-2">
                  <button className="font-medium text-blue-700 hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(a.agent_id); }}>{a.agent_id}</button>
                </td>
                <td className="px-3 py-2 text-slate-600">{a.district}<span className="block text-[11px] text-slate-400">{titleCase(a.location_cluster)} · {a.agent_volume_segment}</span></td>
                <td className="num px-3 py-2 text-right">{bdt(a.status_quo_cash).replace("BDT ", "")} → <b>{bdt(a.recommended_cash).replace("BDT ", "")}</b> <Delta v={a.cash_delta} /></td>
                <td className="num px-3 py-2 text-right">{bdt(a.status_quo_efloat).replace("BDT ", "")} → <b>{bdt(a.recommended_efloat).replace("BDT ", "")}</b> <Delta v={a.efloat_delta} /></td>
                <td className="num px-3 py-2 text-right text-slate-600">{bdt(a.cash_p90).replace("BDT ", "")} / {bdt(a.efloat_p90).replace("BDT ", "")}</td>
                <td className="min-w-[150px] whitespace-normal px-3 py-2"><Flags a={a} max={2} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Morning plan explanation for ${a.agent_id}`}
        className="h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{a.agent_id}</h2>
            <p className="text-xs text-slate-500">{a.district} · {titleCase(a.location_cluster)} · {a.agent_volume_segment} volume</p>
          </div>
          <button onClick={onClose} aria-label="Close explanation" className="rounded p-1 text-slate-500 hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>
        <div className="mb-3"><Flags a={a} max={4} /></div>
        {RES.map(({ key, label }) => (
          <section key={key} className="mb-3 rounded-lg border border-slate-200 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">{label}</h3>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-slate-500">Current morning allocation</dt><dd className="num text-right">{bdt(a[`status_quo_${key}`])}</dd>
              <dt className="text-slate-500">Predicted full-day P50</dt><dd className="num text-right">{bdt(a[`${key}_p50`])}</dd>
              <dt className="text-slate-500">Predicted full-day P90</dt><dd className="num text-right">{bdt(a[`${key}_p90`])}</dd>
              <dt className="text-slate-500">Recommended allocation</dt><dd className="num text-right font-semibold">{bdt(a[`recommended_${key}`])}</dd>
              <dt className="text-slate-500">Change</dt><dd className="text-right"><Delta v={a[`${key}_delta`]} /></dd>
              <dt className="text-slate-500">P90 coverage before → after</dt>
              <dd className="num text-right">{ratioPct(a[`${key}_coverage_before`])} → {ratioPct(a[`${key}_coverage_after`])}</dd>
            </dl>
            <p className="mt-2 text-xs leading-relaxed text-slate-700">{a.explanation[key]}</p>
          </section>
        ))}
        <section className="mb-3 rounded-lg border border-slate-200 p-3 text-xs leading-relaxed text-slate-700">
          <h3 className="mb-1 font-semibold uppercase tracking-wide text-slate-600">Why this plan</h3>
          {a.explanation.constraint}
        </section>
        <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-xs leading-relaxed text-amber-950">
          <h3 className="mb-1 font-semibold uppercase tracking-wide">Safety</h3>
          {a.explanation.safety} Explanations come from fixed templates over the plan&apos;s numbers — not from a language model
          and not from per-agent causal attribution.
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
  useEffect(() => { setRes(null); setAck(false); setErr(null); }, [plan.date]);
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
    <Card className="mb-4">
      <CardHeader title="Human review" subtitle="Approving runs a simulation and writes an audit entry. Nothing is transferred." right={<SourceTag kind="sim" />} />
      <div className="flex flex-wrap items-center gap-3 p-4 text-sm">
        {res ? (
          <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-emerald-900">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            <b>{res.status}</b>
            <span className="text-xs">
              {res.simulation_id} · cash {bdt(res.conservation.network.cash.status_quo_total_bdt)} → {bdt(res.conservation.network.cash.recommended_total_bdt)} · e-float{" "}
              {bdt(res.conservation.network.efloat.status_quo_total_bdt)} → {bdt(res.conservation.network.efloat.recommended_total_bdt)} · extra working capital BDT{" "}
              {res.conservation.extra_working_capital_bdt}
            </span>
          </div>
        ) : (
          <>
            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              I have reviewed the plan, including the review-focus agents.
            </label>
            <button
              onClick={approve}
              disabled={!ack || busy}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Simulating…" : "Approve Simulation"}
            </button>
            {err && <span className="text-xs text-red-700">{err}</span>}
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

  return (
    <>
      <PageHeader
        title="Morning Liquidity Plan"
        subtitle="Pre-position physical cash and e-float before demand arrives — using the same working capital."
        right={
          dates.data && (
            <label className="flex items-center gap-2 text-xs text-slate-600">
              Plan date
              <select aria-label="Plan date" value={current || ""} onChange={(e) => { setDate(e.target.value); setOpen(null); }} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-800">
                {dates.data.dates.map((d) => (
                  <option key={d} value={d}>{dayLabel(d)}</option>
                ))}
              </select>
            </label>
          )
        }
      />
      <div className="mb-4 flex flex-wrap gap-1.5" aria-label="Trust labels">
        {TRUST.map((t) => (
          <span key={t} className="rounded-full bg-slate-900 px-2.5 py-0.5 text-[11px] font-medium text-white">{t}</span>
        ))}
        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] text-slate-600">Proactive full-day plan · intraday V2 stays reactive</span>
      </div>

      {dates.error && <ErrorState message={dates.error} onRetry={dates.reload} />}
      {plan.error && <ErrorState message={plan.error} onRetry={plan.reload} />}
      {!plan.data && !plan.error && !dates.error && <Loading label="Loading the Morning Plan…" />}
      {dates.data && dates.data.dates.length === 0 && <p className="text-sm text-slate-500">No Morning Plan dates are available.</p>}

      {plan.data && (
        <div className={plan.loading ? "opacity-60 transition-opacity" : ""}>
          <Hero plan={plan.data} />
          <ResourcePlan plan={plan.data} />
          <ReviewFocus plan={plan.data} onOpen={setOpen} />
          <AgentTable plan={plan.data} onOpen={setOpen} />
          <Approval plan={plan.data} />
          <DistrictTable plan={plan.data} />
          <p className="mb-6 text-xs text-slate-400">
            {plan.data.meta.labels.synthetic}. Demo fixture: synthetic seed {plan.data.meta.demo_seed}; frozen model spec{" "}
            {plan.data.meta.frozen_model_spec_commit.slice(0, 7)}. Allocation recomputed live; no performance claim is made for this date.
          </p>
        </div>
      )}
      {ev.data && <MorningEvidencePanel ev={ev.data} />}
      {ev.error && !plan.error && <ErrorState message={ev.error} onRetry={ev.reload} />}
      {agent && <AgentDrawer a={agent} onClose={() => setOpen(null)} />}
    </>
  );
}

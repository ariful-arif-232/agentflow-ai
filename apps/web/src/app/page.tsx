"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Banknote, ChevronRight, CircleAlert, Lightbulb, MousePointerClick, ShieldCheck, Smartphone, Sunrise, UserCheck } from "lucide-react";
import { useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, bdtCompact, dateTime, pct, ratioPct, titleCase } from "@/lib/format";
import type { Overview } from "@/lib/types";
import { NetworkTrendChart, RiskDistributionChart } from "@/components/charts";
import { PRODUCT_TAGLINE } from "@/components/Shell";
import { AnomalyBadge, Card, CardHeader, ErrorState, Eyebrow, Loading, RiskBadge, SourceTag, Tooltip, cx } from "@/components/ui";

/* ------------------------------------------------------------------ hero: two time scales */
const INTRADAY = [
  { label: "Monitor 6-hour cash pressure", href: "/agents" },
  { label: "Explain", href: "/agents" },
  { label: "Recommend V2 recovery", href: "/rebalancing" },
  { label: "Human review", href: "/rebalancing" },
];

function Step({ children, strong = false }: { children: React.ReactNode; strong?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center whitespace-nowrap rounded-md px-2.5 py-1 text-[13px] font-medium",
        strong ? "bg-white font-semibold text-blue-700 ring-1 ring-inset ring-blue-300" : "bg-white text-slate-700 ring-1 ring-inset ring-slate-200",
      )}
    >
      {children}
    </span>
  );
}

function Proof({ icon, value, label, note }: { icon: React.ReactNode; value: string; label: string; note: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200/90 border-l-[3px] border-l-blue-600 bg-white px-4 py-2.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sun-100 text-navy-900 ring-1 ring-inset ring-sun-400/60">{icon}</div>
      <div className="min-w-0 leading-snug">
        <div className="text-[13px] text-slate-600">
          <span className="num mr-1.5 text-[15px] font-semibold text-navy-900">{value}</span>
          {label}
        </div>
        <div className="text-xs text-slate-500">{note}</div>
      </div>
    </div>
  );
}

function Lane({ icon, title, children, accent = false }: { icon: React.ReactNode; title: string; children: React.ReactNode; accent?: boolean }) {
  return (
    <div className={cx("flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-xl px-4 py-2.5 ring-1 ring-inset", accent ? "bg-sun-50 ring-sun-400/50" : "bg-blue-50/70 ring-blue-200/80")}>
      <span className={cx("flex w-[88px] shrink-0 items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em]", accent ? "text-sun-800" : "text-blue-700")}>
        {icon} {title}
      </span>
      {children}
    </div>
  );
}

/* Decorative hero backdrop (inline SVG, aria-hidden). The wave sits low; the trust illustration only
   renders where the panel has empty space beside the text (container queries), never behind it. */
function slab(cx: number, cy: number, a: number, b: number, t: number, id: string) {
  return (
    <g>
      <path d={`M${cx - a} ${cy} L${cx} ${cy + b} L${cx} ${cy + b + t} L${cx - a} ${cy + t} Z`} fill={`url(#${id}-l)`} />
      <path d={`M${cx} ${cy + b} L${cx + a} ${cy} L${cx + a} ${cy + t} L${cx} ${cy + b + t} Z`} fill={`url(#${id}-r)`} />
      <path d={`M${cx} ${cy - b} L${cx + a} ${cy} L${cx} ${cy + b} L${cx - a} ${cy} Z`} fill={`url(#${id}-t)`} stroke="#ffffff" strokeOpacity="0.8" strokeWidth="0.8" />
    </g>
  );
}

function TrustIllustration({ className, id }: { className: string; id: string }) {
  return (
    <svg viewBox="0 0 160 150" className={className} aria-hidden focusable="false">
      <defs>
        <linearGradient id={`${id}-t`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#F2F8FF" /><stop offset="1" stopColor="#BFDFFF" /></linearGradient>
        <linearGradient id={`${id}-l`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#9CCBFF" stopOpacity="0.85" /><stop offset="1" stopColor="#78B7FF" stopOpacity="0.7" /></linearGradient>
        <linearGradient id={`${id}-r`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5C99F8" stopOpacity="0.75" /><stop offset="1" stopColor="#2F7CF6" stopOpacity="0.55" /></linearGradient>
        <linearGradient id={`${id}-col`} x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor="#78B7FF" stopOpacity="0.45" /><stop offset="1" stopColor="#DCEEFF" stopOpacity="0" /></linearGradient>
        <radialGradient id={`${id}-glow`}><stop offset="0" stopColor="#2F7CF6" stopOpacity="0.28" /><stop offset="1" stopColor="#2F7CF6" stopOpacity="0" /></radialGradient>
        <radialGradient id={`${id}-sun`}><stop offset="0" stopColor="#F6C51B" stopOpacity="0.38" /><stop offset="1" stopColor="#F6C51B" stopOpacity="0" /></radialGradient>
      </defs>
      <ellipse cx="80" cy="138" rx="74" ry="14" fill={`url(#${id}-glow)`} />
      {slab(80, 120, 58, 16, 11, id)}
      {slab(80, 103, 42, 12, 8, id)}
      <path d="M58 104 V44 L80 36 L102 44 V104 L80 112 Z" fill={`url(#${id}-col)`} />
      <path d="M80 36 V112" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="0.8" />
      <circle cx="80" cy="60" r="30" fill={`url(#${id}-sun)`} />
      <path d="M80 34 L101 41.5 V58 C101 71.5 92 80 80 85 C68 80 59 71.5 59 58 V41.5 Z" fill="#FFF4BF" stroke="#F6C51B" strokeWidth="2.6" strokeLinejoin="round" />
      <path d="M70.5 58.5 L77.5 65.5 L90.5 51.5" fill="none" stroke="#0B1F3A" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GeoPattern() {
  return (
    <svg viewBox="0 0 240 200" preserveAspectRatio="xMaxYMid slice" className="h-full w-full" aria-hidden focusable="false">
      <g stroke="#BFDFFF" strokeOpacity="0.55" strokeWidth="1" fill="none">
        <path d="M20 200 L140 0 M80 200 L200 0 M140 200 L240 30" />
      </g>
      <g stroke="#ffffff" strokeOpacity="0.9" strokeWidth="1">
        <path d="M150 20 L190 45 L150 70 L110 45 Z" fill="#DCEEFF" fillOpacity="0.35" />
        <path d="M200 70 L232 90 L200 110 L168 90 Z" fill="#BFDFFF" fillOpacity="0.28" />
        <path d="M120 95 L150 113 L120 131 L90 113 Z" fill="#EAF4FF" fillOpacity="0.45" />
        <path d="M190 140 L226 162 L190 184 L154 162 Z" fill="#DCEEFF" fillOpacity="0.3" />
      </g>
    </svg>
  );
}

function HeroBackdrop() {
  return (
    <>
      <svg viewBox="0 0 1000 200" preserveAspectRatio="none" className="pointer-events-none absolute inset-x-0 bottom-0 h-[58%] w-full" aria-hidden focusable="false">
        <defs>
          <linearGradient id="afh-w1" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#DCEEFF" stopOpacity="0.75" /><stop offset="0.6" stopColor="#EAF4FF" stopOpacity="0.45" /><stop offset="1" stopColor="#EAF4FF" stopOpacity="0.15" /></linearGradient>
          <linearGradient id="afh-w2" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#CFE6FF" stopOpacity="0.6" /><stop offset="0.55" stopColor="#DCEEFF" stopOpacity="0.35" /><stop offset="1" stopColor="#DCEEFF" stopOpacity="0.1" /></linearGradient>
        </defs>
        <path d="M0 110 C 180 55, 400 165, 640 128 S 900 70, 1000 96 L1000 200 L0 200 Z" fill="url(#afh-w1)" />
        <path d="M0 158 C 230 108, 460 198, 720 164 S 930 122, 1000 140 L1000 200 L0 200 Z" fill="url(#afh-w2)" />
      </svg>
      {/* compact: beside the wrapped heading on ~1280-1366 px screens */}
      <div className="pointer-events-none absolute right-0 top-0 hidden h-[150px] w-[210px] [mask-image:linear-gradient(to_left,black_55%,transparent)] @min-[500px]:block @min-[640px]:hidden">
        <GeoPattern />
      </div>
      <TrustIllustration id="afh-c" className="pointer-events-none absolute right-4 top-10 hidden h-[92px] @min-[500px]:block @min-[640px]:hidden" />
      {/* mid: ~1440-1536 px screens, smaller and quieter, in the lower-right corner below the heading */}
      <div className="pointer-events-none absolute bottom-0 right-0 hidden h-[45%] w-[150px] opacity-60 [mask-image:linear-gradient(to_left,black_45%,transparent)] @min-[640px]:block @min-[880px]:hidden">
        <GeoPattern />
      </div>
      <TrustIllustration id="afh-m" className="pointer-events-none absolute bottom-3 right-3 hidden h-[88px] opacity-80 @min-[640px]:block @min-[880px]:hidden" />
      {/* full: wide screens, to the right of the heading and paragraph */}
      <div className="pointer-events-none absolute inset-y-0 right-0 hidden w-[240px] [mask-image:linear-gradient(to_left,black_50%,transparent)] @min-[880px]:block">
        <GeoPattern />
      </div>
      <TrustIllustration id="afh-f" className="pointer-events-none absolute bottom-2 right-4 hidden h-[150px] @min-[880px]:block" />
    </>
  );
}

function Hero({ snapshot }: { snapshot?: string }) {
  return (
    <section aria-labelledby="hero-title" className="af-rise mb-5 overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_14px_32px_-26px_rgba(23,105,232,0.4)]">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="@container relative flex min-w-0 flex-col justify-center overflow-hidden rounded-xl bg-[linear-gradient(120deg,#ffffff_0%,#f8fbff_38%,#eef6ff_72%,#e9f3ff_100%)] px-5 py-5 ring-1 ring-inset ring-blue-100 sm:px-6">
          <HeroBackdrop />
          <div className="relative @min-[640px]:-my-1 @min-[880px]:my-0">
            <Eyebrow className="text-slate-600">Liquidity operations console{snapshot ? ` · Snapshot ${snapshot}` : ""}</Eyebrow>
            <span aria-hidden className="mt-2 block h-[3px] w-9 rounded-full bg-sun-400" />
            <h1 id="hero-title" className="mt-3 text-[24px] font-semibold leading-[1.15] tracking-tight text-navy-900 sm:text-[28px] 2xl:text-[34px]">
              {/* each sentence stays whole, so a narrow screen breaks the line between the two sentences */}
              {PRODUCT_TAGLINE.split(/(?<=\.)\s/).map((sentence, i) => (
                <span key={i}>
                  {i > 0 && " "}
                  <span className="inline-block">{sentence}</span>
                </span>
              ))}
            </h1>
            <p className="mt-2.5 max-w-[54rem] text-pretty text-[15px] leading-relaxed text-slate-600 @min-[640px]:max-w-[calc(100%-7.5rem)] @min-[880px]:max-w-[48rem]">
              Plan where each agent&apos;s physical cash and e-float should sit before the day starts, then watch intraday cash pressure and
              recommend safe recovery. A person reviews every consequential action.
            </p>
          </div>
        </div>
        <div className="grid content-center gap-2.5" aria-label="Guarantees by design">
          <Proof icon={<Banknote className="h-4 w-4" aria-hidden />} value="BDT 0" label="extra working capital" note="Morning Plan repositions the same district budgets" />
          <Proof icon={<Smartphone className="h-4 w-4" aria-hidden />} value="Cash + E-float" label="planned separately" note="Morning Plan positions both — never swapped" />
          <Proof icon={<UserCheck className="h-4 w-4" aria-hidden />} value="Human reviewed" label="no automatic transfers" note="Approval only runs a simulation" />
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <Lane icon={<Sunrise className="h-4 w-4" aria-hidden />} title="Morning" accent>
          <div className="flex flex-wrap items-center gap-1.5" aria-label="Morning time scale">
            <Step strong>07:00 Predict</Step>
            <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden />
            <Step strong>08:00 Position cash + e-float</Step>
          </div>
          <span className="text-xs text-slate-600">
            <span className="font-semibold text-navy-900">Before the day starts:</span>
            <span className="hidden 2xl:inline"> full-day positioning,</span> same working capital.
          </span>
          <Link
            href="/morning-plan"
            className="ml-auto inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-blue-600 px-3 py-1.5 text-[13px] font-semibold text-white shadow-sm transition-colors hover:bg-blue-700"
          >
            Open Morning Plan <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Lane>
        <Lane icon={<AlertTriangle className="h-4 w-4" aria-hidden />} title="Intraday">
          <nav className="flex flex-wrap items-center gap-1.5" aria-label="Intraday decision loop">
            {INTRADAY.map((s, i) => (
              <span key={s.label} className="flex items-center gap-1.5">
                <Link href={s.href} className="rounded-md transition-opacity hover:opacity-80">
                  <Step>{s.label}</Step>
                </Link>
                {i < INTRADAY.length - 1 && <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden />}
              </span>
            ))}
          </nav>
        </Lane>
      </div>
      <p className="mt-2.5 text-xs text-slate-500">
        Intraday loop: <i>Predict. Explain. Rebalance.</i> (physical cash only). Morning and intraday are evaluated in two separate synthetic
        environments; their results are never combined.
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ attention → recommendation → action */
function DecisionColumn({ n, title, question, icon, children, tone = "default" }: { n: number; title: string; question: string; icon: React.ReactNode; children: React.ReactNode; tone?: "default" | "attention" | "action" }) {
  return (
    <section
      aria-label={title}
      className={cx(
        "af-rise flex flex-col rounded-xl border bg-white px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]",
        tone === "attention" ? "border-orange-200" : tone === "action" ? "border-blue-200" : "border-slate-200/90",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-navy-900 text-xs font-semibold text-white">{n}</span>
        <Eyebrow className="text-slate-700">{title}</Eyebrow>
        <span className="ml-auto text-slate-400">{icon}</span>
      </div>
      <p className="mt-1 text-[13px] text-slate-500">{question}</p>
      <div className="mt-2 flex flex-1 flex-col">{children}</div>
    </section>
  );
}

export default function CommandCenter() {
  const { asOf } = useAsOf();
  const { data, error, loading, reload } = useApi<Overview>(asOf ? "/api/overview" : null, { as_of: asOf });
  const k = data?.kpis;

  return (
    <>
      <h1 className="sr-only">Command Center</h1>
      <Hero snapshot={data ? dateTime(data.as_of) : undefined} />
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Loading />}
      {data && k && (
        <div className={loading ? "opacity-60 transition-opacity" : ""}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">Right now · next {data.horizon_hours} hours</h2>
            <span className="text-xs text-slate-500">Intraday cash view · {dateTime(data.as_of)}</span>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <DecisionColumn n={1} title="Attention" question="Where is risk?" icon={<AlertTriangle className="h-4 w-4" aria-hidden />} tone="attention">
              <div className="flex items-end gap-2">
                <span className="num text-[40px] font-semibold leading-none tracking-tight text-orange-600">{k.at_risk_agents}</span>
                <span className="mb-1 flex items-center gap-1 text-sm font-medium text-slate-700">
                  agents at risk <Tooltip text={data.kpi_definitions.at_risk_agents} />
                </span>
              </div>
              <ul className="mt-3 flex flex-wrap gap-2 text-[13px] text-slate-700" aria-label="Risk breakdown">
                <li className="inline-flex items-center gap-1.5 rounded-lg bg-red-50 px-2.5 py-1 ring-1 ring-inset ring-red-200">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-600" aria-hidden />
                  <span>
                    <b className="num font-semibold text-red-700">{k.critical_agents} critical</b> (risk score ≥ 75)
                  </span>
                </li>
                <li className="inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1 ring-1 ring-inset ring-amber-200">
                  <CircleAlert className="h-3.5 w-3.5 shrink-0 text-amber-700" aria-hidden />
                  <span>
                    <b className="num font-semibold text-slate-900">{k.medium_risk_agents}</b> more at MEDIUM
                  </span>
                </li>
              </ul>
              <div className="mt-auto pt-3">
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  Projected service readiness <Tooltip text={data.kpi_definitions.projected_service_availability_pct} />
                </div>
                <div className="num mt-0.5 text-[15px] font-semibold text-slate-900">
                  {pct(k.projected_service_availability_pct, 1)} <ArrowRight className="inline h-3.5 w-3.5 text-slate-400" aria-label="to" />{" "}
                  <span className="text-blue-700">{pct(k.projected_service_availability_after_plan_pct, 1)}</span>
                  <span className="ml-1 text-xs font-normal text-slate-500">with recommended plan</span>
                </div>
              </div>
            </DecisionColumn>

            <DecisionColumn n={2} title="Recommendation" question="What does AgentFlow recommend?" icon={<Lightbulb className="h-4 w-4" aria-hidden />}>
              <div className="flex items-end gap-2">
                <span className="num text-[34px] font-semibold leading-none tracking-tight text-slate-900">{bdtCompact(k.recommended_rebalancing_value)}</span>
              </div>
              <div className="mt-1 text-sm font-medium text-slate-700">
                {k.n_recommendations} safe peer transfers · policy {k.rebalancing_policy.toUpperCase()}
              </div>
              <div className="space-y-1 pt-3 text-[13px] text-slate-600">
                <div>
                  <b className="num text-slate-800">{bdtCompact(k.escalated_amount)}</b> escalated to the distributor (no safe peer surplus)
                </div>
                <div className="flex items-center gap-1">
                  Expected shortfall without action <b className="num text-slate-800">{bdtCompact(k.total_expected_shortfall)}</b>
                </div>
              </div>
            </DecisionColumn>

            <DecisionColumn n={3} title="Action" question="What should the operator do next?" icon={<MousePointerClick className="h-4 w-4" aria-hidden />} tone="action">
              <p className="text-sm leading-snug text-slate-800">
                Review the policy {k.rebalancing_policy.toUpperCase()} plan: <b>{k.n_recommendations} peer transfers</b> for at-risk agents, with need the peers
                cannot cover escalated to the distributor.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  href="/rebalancing"
                  className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
                >
                  Review recommendations <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
                {data.top_at_risk[0] && (
                  <Link
                    href={`/agents/${data.top_at_risk[0].agent_id}`}
                    className="inline-flex items-center gap-1.5 rounded-md bg-white px-3.5 py-2 text-sm font-medium text-slate-800 ring-1 ring-inset ring-slate-300 transition-colors hover:bg-slate-50"
                  >
                    Highest-risk agent ({data.top_at_risk[0].agent_id}) <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                )}
              </div>
              <p className="mt-auto flex items-center gap-1.5 pt-3 text-xs text-slate-500">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                Every action is reviewed by a person; approval only runs a simulation.
              </p>
            </DecisionColumn>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Network snapshot">
            {[
              { label: "Active agents", value: String(k.active_agents), sub: "in the synthetic network" },
              { label: "With unusual activity", value: String(k.anomaly_watch_agents), sub: "routed to manual review, not fraud" },
              { label: "Forecast 6h cash demand", value: bdtCompact(k.forecast_cash_demand_6h), sub: "network cash-out, next 6 hours", tip: data.kpi_definitions.forecast_cash_demand_6h },
              { label: "Expected shortfall", value: bdtCompact(k.total_expected_shortfall), sub: "before any recommended action" },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-slate-200/90 bg-white px-4 py-3">
                <div className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-slate-500">
                  {s.label}
                  {s.tip && <Tooltip text={s.tip} />}
                </div>
                <div className="num mt-1 text-xl font-semibold tracking-tight text-slate-900">{s.value}</div>
                <div className="text-xs text-slate-500">{s.sub}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 2xl:grid-cols-5">
            <Card className="2xl:col-span-3">
              <CardHeader
                title="Top at-risk agents"
                subtitle="Ranked by liquidity risk score"
                right={
                  <Link href="/agents" className="flex items-center gap-1 whitespace-nowrap text-sm font-medium text-blue-700 hover:underline">
                    All agents <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              />
              <div className="overflow-x-auto">
                <table className="w-full whitespace-nowrap text-sm">
                  <thead className="bg-slate-50 text-left text-xs text-slate-500">
                    <tr>
                      <th className="px-4 py-2 font-medium">Agent</th>
                      <th className="px-4 py-2 font-medium">Location</th>
                      <th className="px-4 py-2 text-right font-medium">Cash</th>
                      <th className="px-4 py-2 text-right font-medium">6h requirement</th>
                      <th className="px-4 py-2 text-right font-medium">Coverage</th>
                      <th className="px-4 py-2 font-medium">Risk</th>
                      <th className="px-4 py-2 font-medium">Behaviour</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.top_at_risk.map((a) => (
                      <tr key={a.agent_id} className="transition-colors hover:bg-slate-50">
                        <td className="px-4 py-2.5">
                          <Link href={`/agents/${a.agent_id}`} className="font-medium text-blue-700 hover:underline">
                            {a.agent_id}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5 text-slate-600">
                          {a.district} · {titleCase(a.location_cluster)}
                        </td>
                        <td className="num px-4 py-2.5 text-right">{bdt(a.cash_balance)}</td>
                        <td className="num px-4 py-2.5 text-right">{bdt(a.pred_net_requirement_6h)}</td>
                        <td className="num px-4 py-2.5 text-right">{ratioPct(a.coverage_ratio)}</td>
                        <td className="px-4 py-2.5">
                          <RiskBadge level={a.risk_level} score={a.risk_score} />
                        </td>
                        <td className="px-4 py-2.5">
                          <AnomalyBadge status={a.anomaly_status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card className="2xl:col-span-2">
              <CardHeader
                title="Urgent rebalancing recommendations"
                subtitle="Peer transfers awaiting human review"
                right={
                  <Link href="/rebalancing" className="flex items-center gap-1 whitespace-nowrap text-sm font-medium text-blue-700 hover:underline">
                    Review <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              />
              <ul className="divide-y divide-slate-100">
                {data.urgent_recommendations.length === 0 && <li className="px-5 py-4 text-sm text-slate-500">No recommendations at this time.</li>}
                {data.urgent_recommendations.map((r) => (
                  <li key={r.id} className="px-5 py-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-slate-900">
                        {r.source_agent} → {r.destination_agent}
                      </span>
                      <span className="num font-semibold text-slate-900">{bdt(r.recommended_amount)}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span>{r.district}</span>·<span>{r.distance_km.toFixed(1)} km</span>·
                      <RiskBadge level={r.destination_risk_before.risk_level} score={r.destination_risk_before.risk_score} />
                      <ArrowRight className="h-3 w-3" aria-label="to" />
                      <RiskBadge level={r.destination_risk_after.risk_level} score={r.destination_risk_after.risk_score} />
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader
                title="Network cash-out demand — last 48 hours"
                subtitle="Bars: actual hourly cash-out. Lines: the 6-hour forecast made at each hour vs. what actually happened (shown only once observable)."
                right={<SourceTag kind="model" />}
              />
              <div className="p-3">
                <NetworkTrendChart data={data.demand_trend} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Liquidity risk distribution" subtitle="Deterministic 0–100 risk score from forecast coverage" right={<SourceTag kind="calc" />} />
              <div className="p-3">
                <RiskDistributionChart data={data.risk_distribution} />
              </div>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader title="District overview" subtitle="Forecast demand and risk concentration by district" />
            <div className="overflow-x-auto">
              <table className="w-full whitespace-nowrap text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">District</th>
                    <th className="px-4 py-2 text-right font-medium">Agents</th>
                    <th className="px-4 py-2 text-right font-medium">At risk</th>
                    <th className="px-4 py-2 text-right font-medium">Forecast 6h cash demand</th>
                    <th className="px-4 py-2 text-right font-medium">Expected shortfall</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.districts.map((d) => (
                    <tr key={d.district}>
                      <td className="px-4 py-2">{d.district}</td>
                      <td className="num px-4 py-2 text-right">{d.agents}</td>
                      <td className="num px-4 py-2 text-right font-medium text-orange-700">{d.at_risk}</td>
                      <td className="num px-4 py-2 text-right">{bdt(d.forecast_demand)}</td>
                      <td className="num px-4 py-2 text-right">{bdt(d.expected_shortfall)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <p className="mt-4 text-xs text-slate-500">{data.data_label}</p>
        </div>
      )}
    </>
  );
}

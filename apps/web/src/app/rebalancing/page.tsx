"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, Circle, ShieldCheck, X, XCircle } from "lucide-react";
import { apiPost, useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, bdtCompact, dateTime, pct } from "@/lib/format";
import type { Plan, PolicyName, Recommendation, SimulationResult } from "@/lib/types";
import { Card, CardHeader, ErrorState, Eyebrow, Kpi, Loading, PageHeader, RiskBadge, SourceTag, cx } from "@/components/ui";
import { CostEquation, CostProxyNote, bdt2, sumParts } from "@/components/LogisticsCost";

interface AuditEntry {
  simulation_id: string;
  created_at: string;
  as_of: string;
  recommendation_ids: string[];
  total_amount: number;
  reviewer_note: string | null;
  status: string;
}

function ReserveBar({ before, after, protectedLevel, label }: { before: number; after: number; protectedLevel?: number; label: string }) {
  const max = Math.max(before, after, protectedLevel || 0, 1);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span className="num text-slate-800">
          {bdt(before)} → <b>{bdt(after)}</b>
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-slate-100">
        <div className="absolute h-2.5 rounded-full bg-slate-300" style={{ width: `${(100 * before) / max}%` }} />
        <div className="absolute h-2.5 rounded-full bg-blue-600/80" style={{ width: `${(100 * after) / max}%` }} />
        {protectedLevel !== undefined && (
          <div className="absolute -top-1 h-4.5 w-0.5 bg-red-500" style={{ left: `${(100 * protectedLevel) / max}%` }} title="Protected level" />
        )}
      </div>
      {protectedLevel !== undefined && <div className="mt-1 text-[11px] text-red-600">Red marker: donor protected level {bdt(protectedLevel)} — never crossed</div>}
    </div>
  );
}

function Evidence({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <dl className="space-y-1.5 text-sm">{children}</dl>
    </section>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <dt className="text-slate-500">{k}</dt>
      <dd className="num text-right text-slate-900">{children}</dd>
    </div>
  );
}

function RiskChange({ a, b }: { a: { risk_level: Recommendation["destination_risk_before"]["risk_level"]; risk_score: number }; b: { risk_level: Recommendation["destination_risk_before"]["risk_level"]; risk_score: number } }) {
  return (
    <span className="inline-flex items-center gap-1">
      <RiskBadge level={a.risk_level} score={a.risk_score} />
      <ArrowRight className="h-3 w-3 text-slate-400" aria-label="to" />
      <RiskBadge level={b.risk_level} score={b.risk_score} />
    </span>
  );
}

/* ------------------------------------------------------------------ V2 safety gate
   Built only from fields already on the recommendation; nothing is recomputed by a model. */
type GateState = "pass" | "fail" | "pending";
interface GateCheck {
  label: string;
  detail: string;
  state: GateState;
}

function gateChecks(rec: Recommendation, approved: boolean): GateCheck[] {
  const p50Short = Math.max(rec.destination_requirement_p50 - rec.destination_cash_before, 0);
  const before = rec.destination_risk_before;
  const after = rec.destination_risk_after;
  const needs = before.risk_level === "HIGH" || before.risk_level === "CRITICAL" || p50Short > 0;
  const margin = rec.donor_margin_after_plan ?? rec.source_cash_after - rec.source_protected_level;
  const donorSafe = rec.source_risk_after.risk_level === "LOW" && margin >= 0;
  const helps = after.risk_score < before.risk_score && (!rec.expected_benefit || !!rec.expected_benefit.gate_reason);
  return [
    {
      label: "Recipient needs help",
      detail: `${before.risk_level} ${before.risk_score.toFixed(0)}${p50Short > 0 ? ` · shortfall ${bdt(p50Short)}` : ""}`,
      state: needs ? "pass" : "fail",
    },
    {
      label: "Donor remains safe",
      detail: `${rec.source_risk_after.risk_level} after · ${bdt(margin)} above reserve`,
      state: donorSafe ? "pass" : "fail",
    },
    {
      label: "Transfer materially helps",
      detail: rec.expected_benefit ? rec.expected_benefit.gate_reason : `risk ${before.risk_score.toFixed(0)} → ${after.risk_score.toFixed(0)}`,
      state: helps ? "pass" : "fail",
    },
    {
      label: "Logistics considered",
      detail: `${rec.distance_km.toFixed(1)} km · cost proxy ${bdt(rec.logistics_cost.total_estimated_cost_bdt)}`,
      state: "pass",
    },
    {
      label: "Human review required",
      detail: approved ? "Simulation approved" : "awaiting a reviewer",
      state: approved ? "pass" : "pending",
    },
  ];
}

function PlanCostCard({ recs, lg, phase1 }: { recs: Recommendation[]; lg: NonNullable<Plan["summary"]["logistics"]>; phase1: number }) {
  const parts = sumParts(recs.map((r) => r.logistics_cost));
  const a = lg.assumptions;
  return (
    <Card className="mt-4">
      <CardHeader
        title="Operational cost breakdown"
        subtitle="distance + field time + handling + cash-in-transit exposure = estimated logistics cost, for every recommended transfer in this plan."
        right={<SourceTag kind="calc" />}
      />
      <div className="space-y-3 px-5 py-4">
        <CostEquation parts={parts} total={lg.peer_transfer_cost_bdt} />
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-[13px] text-slate-700 sm:grid-cols-3">
          <div>
            Peer transfers: <b className="num">{recs.length}</b> · average <b className="num">{bdt2(lg.average_cost_per_transfer_bdt)}</b>
          </div>
          <div>
            Distributor escalations (proxy): <b className="num">{bdt2(lg.escalation_replenishment_cost_bdt)}</b> · {lg.escalations_costed} trips
            {lg.escalations_cost_unavailable > 0 && ` · ${lg.escalations_cost_unavailable} unavailable`}
          </div>
          <div>
            Total operational cost proxy: <b className="num">{bdt2(lg.total_operational_cost_bdt)}</b>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Assumptions: BDT {a.base_handling_bdt} handling · round trip ×{a.distance_multiplier} · BDT {a.per_km_operating_cost_bdt}/km · {a.average_field_speed_kmh} km/h ·{" "}
          {a.handling_time_minutes} min handling · BDT {a.field_officer_cost_per_hour_bdt}/h field time · cash-in-transit {a.cash_in_transit_bps} bps. Escalations are
          costed from a synthetic district hub (district centroid), not a real distributor location. Phase-1 estimate for the same transfers: {bdt(phase1)}.
        </p>
        <CostProxyNote />
      </div>
    </Card>
  );
}

function SafetyGate({ rec, approved = false, compact = false }: { rec: Recommendation; approved?: boolean; compact?: boolean }) {
  const checks = gateChecks(rec, approved);
  return (
    <ol aria-label={`Safety gate for ${rec.id}`} className={cx("grid gap-2", compact ? "sm:grid-cols-2" : "sm:grid-cols-3 xl:grid-cols-5")}>
      {checks.map((c) => {
        const Icon = c.state === "pass" ? CheckCircle2 : c.state === "fail" ? XCircle : Circle;
        return (
          <li
            key={c.label}
            className={cx(
              "flex items-start gap-2 rounded-lg border px-3 py-2",
              c.state === "pass" ? "border-emerald-200 bg-emerald-50/60" : c.state === "fail" ? "border-amber-300 bg-amber-50" : "border-sun-400 border-dashed bg-sun-50",
            )}
          >
            <Icon
              className={cx("mt-0.5 h-4 w-4 shrink-0", c.state === "pass" ? "text-emerald-600" : c.state === "fail" ? "text-amber-700" : "text-slate-600")}
              aria-hidden
            />
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-slate-900">
                {c.label}
                <span className="sr-only">: {c.state === "pass" ? "passed" : c.state === "fail" ? "not met" : "pending"}</span>
              </span>
              <span className="block text-xs leading-snug text-slate-600">{c.detail}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function FocusCard({ rec, policy, approved, onReview }: { rec: Recommendation; policy: PolicyName; approved: boolean; onReview: () => void }) {
  return (
    <Card className="af-rise mb-4 border-blue-200 border-t-[3px] border-t-sun-400">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0">
          <Eyebrow className="text-blue-700">Next recommendation to review · policy {policy.toUpperCase()}</Eyebrow>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-xl font-semibold tracking-tight text-slate-900">
              {rec.source_agent} <ArrowRight className="inline h-4 w-4 text-slate-400" aria-label="to" /> {rec.destination_agent}
            </span>
            <span className="num text-xl font-semibold text-slate-900">{bdt(rec.recommended_amount)}</span>
            <span className="font-mono text-xs text-slate-400">{rec.id}</span>
            <RiskChange a={rec.destination_risk_before} b={rec.destination_risk_after} />
          </div>
          <p className="mt-1 text-[13px] text-slate-500">
            Constrained decision support — not &ldquo;send money to the nearest agent&rdquo;. Every check below comes from this recommendation&apos;s own evidence.
          </p>
        </div>
        {approved ? (
          <span className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden /> Simulation approved
          </span>
        ) : (
          <button onClick={onReview} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700">
            Review Recommendation
          </button>
        )}
      </div>
      <div className="px-5 py-4">
        <SafetyGate rec={rec} approved={approved} />
      </div>
    </Card>
  );
}

function ReviewPanel({
  rec,
  onClose,
  onApproved,
  asOf,
  policy,
}: {
  rec: Recommendation;
  onClose: () => void;
  onApproved: (r: SimulationResult) => void;
  asOf: string;
  policy: PolicyName;
}) {
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const approve = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiPost<SimulationResult>("/api/rebalancing/simulate", {
        recommendation_ids: [rec.id],
        reviewer_acknowledged: ack, // the API rejects approvals without explicit acknowledgement
        reviewer_note: note || null,
        as_of: asOf,
        policy,
      });
      onApproved(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  };
  const p50 = rec.destination_requirement_p50;
  const p90 = rec.destination_requirement_p90;
  const target = rec.destination_target_cash ?? p90;
  const need = Math.max(target - rec.destination_cash_before, 0);
  const coversNeed = rec.destination_cash_after >= target - 500;
  const margin = rec.donor_margin_after_plan ?? rec.source_cash_after - rec.source_protected_level;
  const isV2 = !!rec.expected_benefit;
  return (
    <div className="af-backdrop fixed inset-0 z-40 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-title"
        className="af-drawer h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 id="review-title" className="text-lg font-semibold">
                Review {rec.id}
              </h2>
              <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">Policy {policy.toUpperCase()}</span>
              <SourceTag kind="rec" />
            </div>
            <p className="text-xs text-slate-500">Recommended liquidity rebalancing · human review required</p>
          </div>
          <button ref={closeRef} onClick={onClose} aria-label="Close review" className="rounded p-1 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-4 px-6 py-5">
          <div className="flex items-center justify-between rounded-lg bg-slate-50 p-4">
            <div className="text-sm">
              <div className="text-xs text-slate-500">Donor</div>
              <Link href={`/agents/${rec.source_agent}`} className="font-semibold text-blue-700 hover:underline">
                {rec.source_agent}
              </Link>
            </div>
            <div className="text-center">
              <div className="num text-lg font-semibold">{bdt(rec.recommended_amount)}</div>
              <div className="flex items-center justify-center gap-1 text-xs text-slate-500">
                <ArrowRight className="h-3 w-3" aria-hidden /> {rec.distance_km.toFixed(1)} km · {rec.district} · cost proxy {bdt(rec.logistics_cost.total_estimated_cost_bdt)}
              </div>
            </div>
            <div className="text-right text-sm">
              <div className="text-xs text-slate-500">Recipient</div>
              <Link href={`/agents/${rec.destination_agent}`} className="font-semibold text-blue-700 hover:underline">
                {rec.destination_agent}
              </Link>
            </div>
          </div>

          <section aria-label="Safety gate">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Safety gate</h3>
            <SafetyGate rec={rec} compact />
          </section>

          <Evidence title={`Why this recipient? — ${rec.destination_agent}`}>
            <Row k="Liquidity risk (after full plan)">
              <RiskChange a={rec.destination_risk_before} b={rec.destination_risk_after} />
            </Row>
            <Row k="Expected shortfall (P50 forecast)">
              {bdt(Math.max(p50 - rec.destination_cash_before, 0))} → <b>{bdt(Math.max(p50 - rec.destination_cash_after, 0))}</b>
            </Row>
            <Row k="Cautious P90 coverage">
              {p90 > 0 ? `${Math.round((100 * rec.destination_cash_before) / p90)}% → ${Math.round((100 * rec.destination_cash_after) / p90)}%` : "—"}
            </Row>
            {isV2 && <Row k="Minimum-benefit gate">✓ this transfer {rec.expected_benefit!.gate_reason}</Row>}
          </Evidence>

          <Evidence title={`Why this donor? — ${rec.source_agent}`}>
            <Row k="Donor risk (before → after full plan)">
              <RiskChange a={rec.source_risk_before} b={rec.source_risk_after} />
            </Row>
            <Row k={isV2 ? "Dynamic protected reserve" : "Protected level (110% of P90)"}>{bdt(rec.source_protected_level)}</Row>
            <Row k="Safety margin left after the complete plan">
              <b className={margin >= 0 ? "text-emerald-700" : "text-red-700"}>{bdt(margin)}</b>
            </Row>
            <div className="pt-1">
              <ReserveBar label="Donor cash (whole plan)" before={rec.source_cash_before} after={rec.source_cash_after} protectedLevel={rec.source_protected_level} />
            </div>
            <Row k="Why preferred">
              {isV2 && rec.candidate_rank_key ? (
                <span className="text-xs">
                  {rec.candidate_rank_key.covers_remaining_need ? "covers the whole need alone" : "largest useful amount"} · {rec.candidate_rank_key.risk_points_per_bdt100_cost.toFixed(1)} risk pts
                  removed per BDT 100 cost
                </span>
              ) : (
                <span className="text-xs">nearest eligible LOW-risk donor (V1)</span>
              )}
            </Row>
          </Evidence>

          <Evidence title="Why this amount?">
            <Row k={`Target cash for ${rec.destination_agent}`}>
              {bdt(target)} <span className="text-xs text-slate-500">({isV2 ? "policy target" : "P90 forecast"})</span>
            </Row>
            <Row k="Current cash → need">
              {bdt(rec.destination_cash_before)} → need {bdt(need)}
            </Row>
            <Row k="This transfer">
              {bdt(rec.recommended_amount)}
              {rec.legs_for_destination > 1 ? ` (1 of ${rec.legs_for_destination} transfers)` : coversNeed ? " (covers the need in one transfer)" : ""}
            </Row>
          </Evidence>

          <section className="space-y-2 rounded-lg border border-slate-200 p-4" aria-labelledby="cost-title">
            <h3 id="cost-title" className="text-xs font-semibold uppercase tracking-wide text-slate-500">Operational cost breakdown</h3>
            <CostEquation
              parts={rec.logistics_cost}
              total={rec.logistics_cost.total_estimated_cost_bdt}
              details={{
                distance_cost_bdt: `${rec.logistics_cost.billable_distance_km.toFixed(1)} km (${rec.logistics_cost.travel_distance_km.toFixed(1)} km × ${rec.logistics_cost.distance_multiplier})`,
                time_cost_bdt: `${Math.round(rec.logistics_cost.travel_time_minutes + rec.logistics_cost.handling_time_minutes)} min`,
                cash_in_transit_cost_bdt: `on ${bdt(rec.recommended_amount)}`,
              }}
            />
            <p className="text-xs text-slate-500">
              Phase-1 estimate for comparison: {bdt(rec.estimated_cost_bdt)} (BDT 150 + BDT 25/km).
              {isV2 &&
                (rec.candidate_rank_key?.ranking_cost_model === "logistics_proxy"
                  ? " This plan ranks donors by the cost proxy (experimental ranking)."
                  : " V2 ranks donors with the proven Phase-1 cost; this proxy is used for operational costing.")}
            </p>
            <CostProxyNote />
          </section>

          <details className="rounded-lg border border-slate-200 p-3 text-sm">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-500">Full deterministic explanation</summary>
            <p className="mt-2 leading-relaxed text-slate-700">{rec.reason}</p>
          </details>

          <div className="rounded-lg border border-slate-300 bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ShieldCheck className="h-4 w-4 text-emerald-700" aria-hidden /> Human review · Simulation only — no money moves
            </div>
            <p className="mt-1 text-xs text-slate-600">
              Approving runs a what-if simulation of this transfer and records it in the audit log. No payment instruction is sent.
            </p>
            <textarea
              aria-label="Reviewer note (optional)"
              className="mt-3 w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
              placeholder="Reviewer note (optional)"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <label className="mt-2 flex items-center gap-2 text-sm text-slate-800">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have reviewed the evidence above.
            </label>
            {err && <p className="mt-2 text-xs text-red-700">{err}</p>}
            <button
              disabled={!ack || busy}
              onClick={approve}
              className="mt-3 w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
            >
              {busy ? "Simulating…" : "Approve Simulation"}
            </button>
            <p className="mt-1.5 text-center text-[11px] text-slate-500">Simulation only — no money moves.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function SimulationCard({ sim, onClose }: { sim: SimulationResult; onClose: () => void }) {
  return (
    <Card className="af-confirm mb-4 border-emerald-300">
      <CardHeader
        title={`Simulation approved — no money moved (${sim.simulation_id})`}
        subtitle={`Human-approved simulation of ${sim.recommendation_ids.join(", ")} · ${bdt(sim.total_amount)} · ${dateTime(sim.created_at)} · ${sim.replayed ? "already approved: original audit record shown, no duplicate written" : "recorded in the audit log"}`}
        right={
          <div className="flex items-center gap-2">
            <SourceTag kind="sim" />
            <button onClick={onClose} aria-label="Dismiss simulation result" className="rounded p-1 hover:bg-slate-100">
              <X className="h-4 w-4" />
            </button>
          </div>
        }
      />
      <div className="space-y-4 p-5">
        <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <caption className="sr-only">Projected cash and risk before and after the simulated transfer</caption>
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="pb-1 pr-4 font-medium">Agent</th>
                <th className="pb-1 pr-4 text-right font-medium">Projected cash before → after</th>
                <th className="pb-1 font-medium">Projected risk before → after</th>
              </tr>
            </thead>
            <tbody>
              {sim.agents.map((a) => (
                <tr key={a.agent_id}>
                  <td className="py-1 pr-4">
                    {a.agent_id} <span className="text-xs text-slate-500">({a.role === "destination" ? "recipient" : "donor"})</span>
                  </td>
                  <td className="num py-1 pr-4 text-right">
                    {bdt(a.cash_before)} → {bdt(a.cash_after)}
                  </td>
                  <td className="py-1">
                    <RiskChange a={{ risk_level: a.risk_level_before, risk_score: a.risk_score_before }} b={{ risk_level: a.risk_level_after, risk_score: a.risk_score_after }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          {[
            ["At-risk agents (network)", sim.portfolio_before.at_risk_agents, sim.portfolio_after.at_risk_agents, (x: number) => String(x)],
            ["Expected shortfall (network)", sim.portfolio_before.total_expected_shortfall, sim.portfolio_after.total_expected_shortfall, bdtCompact],
            ["Service readiness (network)", sim.portfolio_before.projected_service_availability_pct, sim.portfolio_after.projected_service_availability_pct, (x: number) => pct(x, 1)],
          ].map(([label, b, a, f]) => (
            <div key={label as string} className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-500">{label as string}</div>
              <div className="num mt-1 text-base font-semibold text-slate-900">
                <span className="text-sm font-normal text-slate-500">{(f as (x: number) => string)(b as number)} → </span>
                {(f as (x: number) => string)(a as number)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function RebalancingInner() {
  const { asOf, demoEpoch } = useAsOf();
  const params = useSearchParams();
  const focus = params.get("focus");
  const [policy, setPolicy] = useState<PolicyName | null>(null);
  const { data, error, loading, reload } = useApi<Plan>(asOf ? "/api/rebalancing/recommendations" : null, { as_of: asOf, policy });
  const activePolicy: PolicyName = policy ?? data?.policy ?? "v2";
  const [auditKey, setAuditKey] = useState(0);
  const audit = useApi<{ simulations: AuditEntry[] }>("/api/rebalancing/audit", { k: auditKey });
  const [reviewing, setReviewing] = useState<Recommendation | null>(null);
  const [sim, setSim] = useState<SimulationResult | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());

  useEffect(() => {
    setApproved(new Set());
    setSim(null);
  }, [asOf, policy]);

  // "Reset demo": restore the default policy (V2) and close transient UI. Client-side only.
  useEffect(() => {
    if (demoEpoch === 0) return;
    setPolicy(null);
    setReviewing(null);
    setSim(null);
    setApproved(new Set());
  }, [demoEpoch]);

  const recs = useMemo(() => {
    if (!data) return [];
    if (!focus) return data.recommendations;
    return [...data.recommendations].sort((a, b) => Number(b.destination_agent === focus) - Number(a.destination_agent === focus));
  }, [data, focus]);

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const s = data.summary;

  return (
    <div className={loading ? "opacity-60" : ""}>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs">
        <span className="font-medium text-slate-500">Rebalancing policy</span>
        {(["v2", "v1"] as PolicyName[]).map((p) => (
          <button
            key={p}
            onClick={() => setPolicy(p)}
            aria-pressed={activePolicy === p}
            className={cx(
              "rounded-md px-3 py-1.5 ring-1 ring-inset focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600",
              activePolicy === p ? "bg-blue-600 text-white ring-blue-600" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50",
            )}
          >
            {p === "v2" ? "V2 — benefit · safety · cost" : "V1 — nearest donor"}
            {data.default_policy === p && " (default)"}
          </button>
        ))}
        <span className="text-slate-500">
          {activePolicy === "v2"
            ? "V2 balances recipient benefit, donor safety and logistics cost."
            : "V1 picks the nearest eligible donors (kept for comparison)."}
        </span>
      </div>
      {recs[0] && <FocusCard rec={recs[0]} policy={activePolicy} approved={approved.has(recs[0].id)} onReview={() => setReviewing(recs[0])} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Recommended transfers" value={s.n_recommendations} sub={`${s.recipients_supported} at-risk agents supported`} />
        <Kpi label="Recommended value" value={bdtCompact(s.total_recommended_amount)} tone="good" sub="peer-to-peer, cash-neutral" />
        <Kpi label="Escalations" value={s.n_escalations} tone="warn" sub={`${bdtCompact(s.escalated_amount)} needs distributor top-up`} />
        <Kpi label="Held for review" value={s.n_held_for_review} sub="unusual activity — no auto-support" />
        <Kpi label="Logistics cost proxy" value={bdt(s.logistics?.peer_transfer_cost_bdt ?? s.estimated_cost_bdt)} sub="peer transfers · synthetic estimate" />
      </div>

      {sim && (
        <div className="mt-4">
          <SimulationCard sim={sim} onClose={() => setSim(null)} />
        </div>
      )}

      <Card className="mt-4">
        <CardHeader
          title="Recommended liquidity rebalancing"
          subtitle={
            activePolicy === "v2"
              ? "Highest-risk recipients first. A transfer is only proposed if it materially helps the recipient; each donor keeps a dynamic reserve (≥110% of its P90 requirement) and stays LOW risk. Nothing executes automatically."
              : "Highest-risk recipients first. Each donor keeps at least 110% of its own P90 forecast requirement. Nothing executes automatically."
          }
          right={<SourceTag kind="rec" />}
        />
        <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-[13px]">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-2.5 py-2 font-medium">Deficit agent</th>
                <th className="px-2.5 py-2 font-medium">Source agent</th>
                <th className="px-2.5 py-2 text-right font-medium">Amount</th>
                <th className="px-2.5 py-2 text-right font-medium">Cash before → after (recipient / donor)</th>
                <th className="px-2.5 py-2 font-medium">Risk before → est. after</th>
                <th className="px-2.5 py-2 font-medium">Safety gate</th>
                <th className="px-2.5 py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recs.map((r) => (
                <tr key={r.id} className={cx("hover:bg-slate-50", focus === r.destination_agent && "bg-blue-50/60")}>
                  <td className="px-2.5 py-2.5">
                    <Link className="font-medium text-blue-700 hover:underline" href={`/agents/${r.destination_agent}`}>
                      {r.destination_agent}
                    </Link>
                  </td>
                  <td className="px-2.5 py-2.5">
                    <Link className="text-blue-700 hover:underline" href={`/agents/${r.source_agent}`}>
                      {r.source_agent}
                    </Link>
                    <div className="text-xs text-slate-500">
                      {r.district} · {r.distance_km.toFixed(1)} km
                    </div>
                  </td>
                  <td className="num px-2.5 py-2.5 text-right">
                    <div className="font-semibold">{bdt(r.recommended_amount)}</div>
                    <div className="font-mono text-[11px] text-slate-400">{r.id}</div>
                  </td>
                  <td className="num px-2.5 py-2.5 text-right text-slate-700">
                    <div>
                      {bdt(r.destination_cash_before)} → {bdt(r.destination_cash_after)}
                    </div>
                    <div className="text-xs text-slate-500">
                      donor {bdt(r.source_cash_before)} → {bdt(r.source_cash_after)}
                    </div>
                  </td>
                  <td className="px-2.5 py-2.5">
                    <span className="inline-flex items-center gap-1">
                      <RiskBadge level={r.destination_risk_before.risk_level} score={r.destination_risk_before.risk_score} />
                      <ArrowRight className="h-3 w-3 text-slate-400" />
                      <RiskBadge level={r.destination_risk_after.risk_level} score={r.destination_risk_after.risk_score} />
                    </span>
                  </td>
                  <td className="px-2.5 py-2.5">
                    {(() => {
                      const auto = gateChecks(r, approved.has(r.id)).slice(0, 4);
                      const ok = auto.filter((c) => c.state === "pass").length;
                      return (
                        <span
                          className={cx(
                            "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
                            ok === auto.length ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20" : "bg-amber-50 text-amber-900 ring-amber-600/25",
                          )}
                          title={auto.map((c) => `${c.label}: ${c.detail}`).join(" · ")}
                        >
                          {ok === auto.length ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : <XCircle className="h-3.5 w-3.5" aria-hidden />}
                          {ok}/{auto.length}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    {approved.has(r.id) ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                        <CheckCircle2 className="h-4 w-4" aria-hidden /> Simulation approved
                      </span>
                    ) : (
                      <button
                        onClick={() => setReviewing(r)}
                        aria-label={`Review Recommendation ${r.id}: ${r.source_agent} to ${r.destination_agent}`}
                        className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700"
                      >
                        Review <ArrowRight className="h-3 w-3" aria-hidden />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {s.logistics && <PlanCostCard recs={recs} lg={s.logistics} phase1={s.estimated_cost_bdt} />}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Escalate to distributor" subtitle="No eligible peer surplus within 15 km in the same district" />
          <ul className="divide-y divide-slate-100 text-sm">
            {data.escalations.length === 0 && <li className="px-5 py-3 text-slate-500">None</li>}
            {data.escalations.map((e) => (
              <li key={e.agent_id} className="flex items-center justify-between px-5 py-2.5">
                <Link className="font-medium text-blue-700 hover:underline" href={`/agents/${e.agent_id}`}>
                  {e.agent_id}
                </Link>
                <span className="text-xs text-slate-500">{e.district}</span>
                <span className="num text-right">
                  {bdt(e.unresolved_need)}
                  <span className="block text-[11px] text-slate-500">
                    {e.replenishment_cost?.available
                      ? `trip proxy ${bdt(e.replenishment_cost.total_estimated_cost_bdt)} · ${e.replenishment_cost.travel_distance_km.toFixed(1)} km from synthetic hub`
                      : "trip cost unavailable"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Held for manual review" subtitle="At-risk agents with unusual behavioural activity" />
          <ul className="divide-y divide-slate-100 text-sm">
            {data.held_for_review.length === 0 && <li className="px-5 py-3 text-slate-500">None</li>}
            {data.held_for_review.map((h) => (
              <li key={h.agent_id} className="px-5 py-2.5">
                <div className="flex justify-between">
                  <Link className="font-medium text-blue-700 hover:underline" href={`/agents/${h.agent_id}`}>
                    {h.agent_id}
                  </Link>
                  <span className="num">need {bdt(h.need)}</span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{h.reason}</p>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Simulation audit log" subtitle="Every simulated approval is recorded once in a tamper-evident, hash-chained log (prototype; process-local)" />
          <ul className="divide-y divide-slate-100 text-sm">
            {(audit.data?.simulations.length ?? 0) === 0 && <li className="px-5 py-3 text-slate-500">No simulations yet.</li>}
            {audit.data?.simulations.slice(0, 8).map((a) => (
              <li key={a.simulation_id} className="px-5 py-2.5">
                <div className="flex justify-between">
                  <span className="font-mono text-xs">{a.simulation_id}</span>
                  <span className="num">{bdt(a.total_amount)}</span>
                </div>
                <div className="text-xs text-slate-500">
                  {a.recommendation_ids.join(", ")} · {dateTime(a.created_at)}
                  {a.reviewer_note && <> · “{a.reviewer_note}”</>}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {reviewing && asOf && (
        <ReviewPanel
          rec={reviewing}
          asOf={asOf}
          policy={activePolicy}
          onClose={() => setReviewing(null)}
          onApproved={(res) => {
            setSim(res);
            setApproved((prev) => new Set(prev).add(reviewing.id));
            setReviewing(null);
            setAuditKey((k) => k + 1);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      )}
    </div>
  );
}

export default function RebalancingPage() {
  return (
    <>
      <PageHeader
        eyebrow="Intraday · reactive physical-cash recovery (V2)"
        title="Rebalancing Center"
        subtitle="Explainable, safety-constrained peer liquidity rebalancing. Review each recommendation's evidence, then approve a simulation — AgentFlow never moves real money."
      />
      <p className="-mt-3 mb-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <b>Morning Plan</b> is proactive full-day positioning of cash and e-float at 08:00. <b>V2</b> (this page) is reactive
        intraday <b>physical-cash</b> rebalancing — it does not optimise e-float.
      </p>
      <Suspense fallback={<Loading />}>
        <RebalancingInner />
      </Suspense>
    </>
  );
}

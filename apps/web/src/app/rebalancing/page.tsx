"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, ShieldCheck, X } from "lucide-react";
import { apiPost, useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, bdtCompact, dateTime, pct, ratioPct } from "@/lib/format";
import type { Plan, PolicyName, Recommendation, SimulationResult } from "@/lib/types";
import { Card, CardHeader, ErrorState, Kpi, Loading, PageHeader, RiskBadge, SourceTag, cx } from "@/components/ui";

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
  const approve = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiPost<SimulationResult>("/api/rebalancing/simulate", { recommendation_ids: [rec.id], reviewer_note: note || null, as_of: asOf, policy });
      onApproved(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={onClose}>
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Review recommendation {rec.id}</h2>
              <SourceTag kind="rec" />
            </div>
            <p className="text-xs text-slate-500">Recommended liquidity rebalancing · human review required</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-slate-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-5 px-6 py-5">
          <div className="flex items-center justify-between rounded-lg bg-slate-50 p-4">
            <div className="text-sm">
              <div className="text-xs text-slate-500">Source (donor)</div>
              <Link href={`/agents/${rec.source_agent}`} className="font-semibold text-blue-700 hover:underline">
                {rec.source_agent}
              </Link>
            </div>
            <div className="text-center">
              <div className="num text-lg font-semibold">{bdt(rec.recommended_amount)}</div>
              <div className="flex items-center gap-1 text-xs text-slate-500">
                <ArrowRight className="h-3 w-3" /> {rec.distance_km.toFixed(1)} km · {rec.district}
              </div>
            </div>
            <div className="text-right text-sm">
              <div className="text-xs text-slate-500">Destination</div>
              <Link href={`/agents/${rec.destination_agent}`} className="font-semibold text-blue-700 hover:underline">
                {rec.destination_agent}
              </Link>
            </div>
          </div>
          <div>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Why this source?</h3>
            <p className="text-sm leading-relaxed text-slate-800">{rec.reason}</p>
          </div>
          {rec.expected_benefit && (
            <div className="grid grid-cols-2 gap-3 rounded-lg border border-teal-200 bg-teal-50/40 p-3 text-sm">
              <div>
                <div className="text-xs text-slate-500">Expected recipient benefit (this transfer)</div>
                <div className="mt-1 flex items-center gap-1">
                  <RiskBadge level={rec.expected_benefit.risk_level_before} score={rec.expected_benefit.risk_score_before} />
                  <ArrowRight className="h-3 w-3 text-slate-400" />
                  <RiskBadge level={rec.expected_benefit.risk_level_after} score={rec.expected_benefit.risk_score_after} />
                </div>
                <div className="num mt-1 text-xs text-slate-600">Expected shortfall −{bdt(rec.expected_benefit.shortfall_reduction_bdt)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Donor margin above its dynamic reserve (after plan)</div>
                <div className="num mt-1 font-semibold text-slate-900">{bdt(rec.donor_margin_after_plan)}</div>
                <div className="text-xs text-slate-600">Reserve scales with forecast uncertainty, velocity and shortage history</div>
              </div>
            </div>
          )}
          <div className="space-y-4">
            <ReserveBar label={`Destination ${rec.destination_agent} cash (whole plan)`} before={rec.destination_cash_before} after={rec.destination_cash_after} />
            <div className="text-xs text-slate-500">
              Forecast 6h peak requirement {bdt(rec.destination_requirement_p50)} · P90 {bdt(rec.destination_requirement_p90)}
              {rec.legs_for_destination > 1 && <> · this destination receives from {rec.legs_for_destination} donors in the plan</>}
            </div>
            <ReserveBar label={`Source ${rec.source_agent} cash (whole plan)`} before={rec.source_cash_before} after={rec.source_cash_after} protectedLevel={rec.source_protected_level} />
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg border border-slate-200 p-3">
              <div className="text-xs text-slate-500">Destination risk</div>
              <div className="mt-1 flex items-center gap-2">
                <RiskBadge level={rec.destination_risk_before.risk_level} score={rec.destination_risk_before.risk_score} />
                <ArrowRight className="h-3 w-3 text-slate-400" />
                <RiskBadge level={rec.destination_risk_after.risk_level} score={rec.destination_risk_after.risk_score} />
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Coverage {ratioPct(rec.destination_risk_before.coverage_ratio)} → {ratioPct(rec.destination_risk_after.coverage_ratio)}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 p-3">
              <div className="text-xs text-slate-500">Source risk</div>
              <div className="mt-1 flex items-center gap-2">
                <RiskBadge level={rec.source_risk_before.risk_level} score={rec.source_risk_before.risk_score} />
                <ArrowRight className="h-3 w-3 text-slate-400" />
                <RiskBadge level={rec.source_risk_after.risk_level} score={rec.source_risk_after.risk_score} />
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Coverage {ratioPct(rec.source_risk_before.coverage_ratio)} → {ratioPct(rec.source_risk_after.coverage_ratio)}
              </div>
            </div>
          </div>
          <div className="text-xs text-slate-500">Estimated logistics cost: {bdt(rec.estimated_cost_bdt)} (fixed BDT 150 + BDT 25/km assumption)</div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-amber-900">
              <ShieldCheck className="h-4 w-4" /> Simulation only
            </div>
            <p className="mt-1 text-xs text-amber-900/80">Approving runs a what-if simulation of this transfer and records it in the audit log. No money is moved and no instruction is sent.</p>
            <textarea
              className="mt-3 w-full rounded-md border border-amber-200 bg-white p-2 text-sm"
              placeholder="Reviewer note (optional)"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <label className="mt-2 flex items-center gap-2 text-xs text-amber-900">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have reviewed the evidence above.
            </label>
            {err && <p className="mt-2 text-xs text-red-700">{err}</p>}
            <button
              disabled={!ack || busy}
              onClick={approve}
              className="mt-3 w-full rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white enabled:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Simulating…" : "Approve Simulation"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SimulationCard({ sim, onClose }: { sim: SimulationResult; onClose: () => void }) {
  return (
    <Card className="mb-4 border-emerald-200">
      <CardHeader
        title={`Simulation ${sim.simulation_id} — ${sim.status}`}
        subtitle={`${sim.recommendation_ids.join(", ")} · ${bdt(sim.total_amount)} · ${dateTime(sim.created_at)}`}
        right={
          <div className="flex items-center gap-2">
            <SourceTag kind="sim" />
            <button onClick={onClose} aria-label="Dismiss" className="rounded p-1 hover:bg-slate-100">
              <X className="h-4 w-4" />
            </button>
          </div>
        }
      />
      <div className="grid grid-cols-1 gap-4 p-5 lg:grid-cols-2">
        <table className="w-full whitespace-nowrap text-sm">
          <thead className="text-left text-xs text-slate-500">
            <tr>
              <th className="pb-1 pr-4 font-medium">Agent</th>
              <th className="pb-1 pr-4 text-right font-medium">Cash before → after</th>
              <th className="pb-1 font-medium">Risk before → after</th>
            </tr>
          </thead>
          <tbody>
            {sim.agents.map((a) => (
              <tr key={a.agent_id}>
                <td className="py-1 pr-4">
                  {a.agent_id} <span className="text-xs text-slate-400">({a.role})</span>
                </td>
                <td className="num py-1 pr-4 text-right">
                  {bdt(a.cash_before)} → {bdt(a.cash_after)}
                </td>
                <td className="py-1">
                  <span className="inline-flex items-center gap-1">
                    <RiskBadge level={a.risk_level_before} score={a.risk_score_before} />
                    <ArrowRight className="h-3 w-3 text-slate-400" />
                    <RiskBadge level={a.risk_level_after} score={a.risk_score_after} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="grid grid-cols-3 gap-3 text-sm">
          {[
            ["At-risk agents", sim.portfolio_before.at_risk_agents, sim.portfolio_after.at_risk_agents, (x: number) => String(x)],
            ["Expected shortfall", sim.portfolio_before.total_expected_shortfall, sim.portfolio_after.total_expected_shortfall, bdtCompact],
            ["Service readiness", sim.portfolio_before.projected_service_availability_pct, sim.portfolio_after.projected_service_availability_pct, (x: number) => pct(x, 1)],
          ].map(([label, b, a, f]) => (
            <div key={label as string} className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-500">{label as string}</div>
              <div className="num mt-1 text-xs text-slate-500 line-through">{(f as (x: number) => string)(b as number)}</div>
              <div className="num text-base font-semibold text-emerald-700">{(f as (x: number) => string)(a as number)}</div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function RebalancingInner() {
  const { asOf } = useAsOf();
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
            className={cx(
              "rounded-md px-3 py-1.5 ring-1 ring-inset",
              activePolicy === p ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50",
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
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Recommended transfers" value={s.n_recommendations} sub={`${s.recipients_supported} at-risk agents supported`} />
        <Kpi label="Recommended value" value={bdtCompact(s.total_recommended_amount)} tone="good" sub="peer-to-peer, cash-neutral" />
        <Kpi label="Escalations" value={s.n_escalations} tone="warn" sub={`${bdtCompact(s.escalated_amount)} needs distributor top-up`} />
        <Kpi label="Held for review" value={s.n_held_for_review} sub="unusual activity — no auto-support" />
        <Kpi label="Est. logistics cost" value={bdt(s.estimated_cost_bdt)} sub="BDT 150 + BDT 25/km per transfer" />
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
                <th className="px-2.5 py-2 text-right font-medium">Source cash before → after</th>
                <th className="px-2.5 py-2 text-right font-medium">Deficit agent cash before → after</th>
                <th className="px-2.5 py-2 font-medium">Risk before → est. after</th>
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
                    {bdt(r.source_cash_before)} → {bdt(r.source_cash_after)}
                  </td>
                  <td className="num px-2.5 py-2.5 text-right text-slate-700">
                    {bdt(r.destination_cash_before)} → {bdt(r.destination_cash_after)}
                  </td>
                  <td className="px-2.5 py-2.5">
                    <span className="inline-flex items-center gap-1">
                      <RiskBadge level={r.destination_risk_before.risk_level} score={r.destination_risk_before.risk_score} />
                      <ArrowRight className="h-3 w-3 text-slate-400" />
                      <RiskBadge level={r.destination_risk_after.risk_level} score={r.destination_risk_after.risk_score} />
                    </span>
                  </td>
                  <td className="px-2.5 py-2.5 text-right">
                    {approved.has(r.id) ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                        <CheckCircle2 className="h-4 w-4" /> Simulated
                      </span>
                    ) : (
                      <button onClick={() => setReviewing(r)} className="w-[92px] whitespace-normal rounded-md bg-slate-900 px-2 py-1 text-[11px] font-medium leading-tight text-white hover:bg-slate-700">
                        Review Recommendation
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

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
                <span className="num">{bdt(e.unresolved_need)}</span>
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
          <CardHeader title="Simulation audit log" subtitle="Every simulated approval is recorded (in-memory, this API session)" />
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
        title="Rebalancing Center"
        subtitle="Explainable, safety-constrained peer liquidity rebalancing. Review each recommendation's evidence, then approve a simulation — AgentFlow never moves real money."
      />
      <Suspense fallback={<Loading />}>
        <RebalancingInner />
      </Suspense>
    </>
  );
}

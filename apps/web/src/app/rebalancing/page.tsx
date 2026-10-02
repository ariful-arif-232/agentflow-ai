"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, ShieldCheck, X } from "lucide-react";
import { apiPost, useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, bdtCompact, dateTime, pct } from "@/lib/format";
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
      const res = await apiPost<SimulationResult>("/api/rebalancing/simulate", { recommendation_ids: [rec.id], reviewer_note: note || null, as_of: asOf, policy });
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
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-title"
        className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl"
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
                <ArrowRight className="h-3 w-3" aria-hidden /> {rec.distance_km.toFixed(1)} km · {rec.district} · est. {bdt(rec.estimated_cost_bdt)}
              </div>
            </div>
            <div className="text-right text-sm">
              <div className="text-xs text-slate-500">Recipient</div>
              <Link href={`/agents/${rec.destination_agent}`} className="font-semibold text-blue-700 hover:underline">
                {rec.destination_agent}
              </Link>
            </div>
          </div>

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
            <Row k="Logistics">
              {rec.distance_km.toFixed(1)} km · est. {bdt(rec.estimated_cost_bdt)} <span className="text-xs text-slate-500">(BDT 150 + 25/km)</span>
            </Row>
          </Evidence>

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
    <Card className="mb-4 border-emerald-300">
      <CardHeader
        title={`Simulation approved — no money moved (${sim.simulation_id})`}
        subtitle={`Human-approved simulation of ${sim.recommendation_ids.join(", ")} · ${bdt(sim.total_amount)} · ${dateTime(sim.created_at)} · recorded in the audit log`}
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
                <th className="px-2.5 py-2 text-right font-medium">Cash before → after (recipient / donor)</th>
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
                  <td className="px-2.5 py-2.5 text-right">
                    {approved.has(r.id) ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                        <CheckCircle2 className="h-4 w-4" aria-hidden /> Simulation approved
                      </span>
                    ) : (
                      <button
                        onClick={() => setReviewing(r)}
                        aria-label={`Review Recommendation ${r.id}: ${r.source_agent} to ${r.destination_agent}`}
                        className="rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
                      >
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

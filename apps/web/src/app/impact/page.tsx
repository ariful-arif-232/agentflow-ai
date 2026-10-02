"use client";

import { Fragment } from "react";
import { useApi } from "@/lib/api";
import { bdt, bdtCompact, num, pct, titleCase } from "@/lib/format";
import type { ImpactResponse, MetricsResponse, MorningPlanEvidence, PolicyMetrics } from "@/lib/types";
import { MorningEvidencePanel } from "@/components/MorningEvidence";
import { CompareBars, DailyImpactChart } from "@/components/charts";
import { Card, CardHeader, ErrorState, Loading, PageHeader, SourceTag, cx } from "@/components/ui";

type PolicyKey = "status_quo" | "naive_rebalancing" | "agentflow" | "agentflow_v2";
const COLS: { key: PolicyKey; label: string }[] = [
  { key: "status_quo", label: "Without AgentFlow" },
  { key: "naive_rebalancing", label: "Naive forecast" },
  { key: "agentflow", label: "AgentFlow V1" },
  { key: "agentflow_v2", label: "AgentFlow V2" },
];

function Delta({ before, after, lowerIsBetter = true, unit = "%" }: { before: number; after: number; lowerIsBetter?: boolean; unit?: string }) {
  const d = unit === "pp" ? after - before : before ? (100 * (after - before)) / before : 0;
  const good = lowerIsBetter ? d < 0 : d > 0;
  const tone = Math.abs(d) < 0.05 ? "text-slate-500" : good ? "text-emerald-600" : "text-red-600";
  return <span className={cx("num text-xs font-semibold", tone)}>{`${d > 0 ? "+" : ""}${d.toFixed(1)}${unit === "pp" ? " pp" : "%"}`}</span>;
}

function MorningPlanResearch() {
  const ev = useApi<MorningPlanEvidence>("/api/morning-plan/evidence");
  return (
    <section aria-label="Full-day Morning Plan research evidence" className="mt-8">
      <h2 className="text-lg font-semibold tracking-tight">Full-day Morning Plan — research evidence</h2>
      <p className="mb-3 mt-1 max-w-4xl text-xs text-slate-500">
        A separate synthetic evaluation environment (Dual-Liquidity World v2, cash and e-float) from the legacy cash-only V1/V2
        results above. These numbers must not be combined with the V1/V2 tables. Same working capital in every policy compared.
      </p>
      {ev.error && <ErrorState message={ev.error} onRetry={ev.reload} />}
      {!ev.data && !ev.error && <Loading />}
      {ev.data && <MorningEvidencePanel ev={ev.data} />}
    </section>
  );
}

function V1V2Glance({ v1, v2 }: { v1: PolicyMetrics; v2: PolicyMetrics }) {
  const n1 = Math.round(((v1.unnecessary_interventions_pct ?? 0) * v1.interventions) / 100);
  const n2 = Math.round(((v2.unnecessary_interventions_pct ?? 0) * v2.interventions) / 100);
  const items: { label: string; a: string; b: string; better: boolean }[] = [
    { label: "Unmet cash demand", a: bdtCompact(v1.unmet_cash_demand_bdt), b: bdtCompact(v2.unmet_cash_demand_bdt), better: v2.unmet_cash_demand_bdt < v1.unmet_cash_demand_bdt },
    { label: "Peer transfers", a: num(v1.interventions), b: num(v2.interventions), better: v2.interventions < v1.interventions },
    { label: "Donor shortage events (6h)", a: num(v1.donor_shortage_events_after_transfer), b: num(v2.donor_shortage_events_after_transfer), better: (v2.donor_shortage_events_after_transfer ?? 0) < (v1.donor_shortage_events_after_transfer ?? 0) },
    { label: "Estimated logistics cost", a: bdt(v1.estimated_logistics_cost_bdt), b: bdt(v2.estimated_logistics_cost_bdt), better: v2.estimated_logistics_cost_bdt < v1.estimated_logistics_cost_bdt },
    { label: "Unnecessary-transfer share", a: pct(v1.unnecessary_interventions_pct, 1), b: pct(v2.unnecessary_interventions_pct, 1), better: (v2.unnecessary_interventions_pct ?? 0) < (v1.unnecessary_interventions_pct ?? 0) },
  ];
  return (
    <Card className="mt-4">
      <CardHeader title="V1 vs V2 at a glance" subtitle="Same held-out period, same demand, same total cash. V2 balances recipient benefit, donor safety and logistics cost." right={<SourceTag kind="sim" />} />
      <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        {items.map((it) => (
          <div key={it.label} className={cx("rounded-lg border p-3", it.better ? "border-emerald-200 bg-emerald-50/50" : "border-amber-300 bg-amber-50/60")}>
            <div className="text-xs text-slate-600">{it.label}</div>
            <div className="num mt-1 text-sm text-slate-500">V1 {it.a}</div>
            <div className="num text-lg font-semibold text-slate-900">V2 {it.b}</div>
            <div className={cx("text-xs font-medium", it.better ? "text-emerald-700" : "text-amber-800")}>{it.better ? "✓ better with V2" : "✗ worse with V2"}</div>
          </div>
        ))}
      </div>
      <p className="border-t border-slate-100 px-4 py-2.5 text-sm text-slate-700">
        <b>Honest limitation:</b> V2 makes fewer transfers overall, so the absolute number of unnecessary transfers falls ({num(n1)} → {num(n2)}), even
        though their share is slightly higher. V2 does not improve every metric; it is also slightly worse than V1 for rural agents.
      </p>
    </Card>
  );
}

export default function ImpactPage() {
  const imp = useApi<ImpactResponse>("/api/impact");
  const met = useApi<MetricsResponse>("/api/model/metrics");
  if (imp.error || met.error) return <ErrorState message={(imp.error || met.error) as string} onRetry={() => { imp.reload(); met.reload(); }} />;
  if (!imp.data || !met.data) return <Loading />;
  const p = imp.data.policies;
  const sq = p.status_quo;
  const dflt = imp.data.deployment_decision.default_policy;
  const af = dflt === "v2" ? p.agentflow_v2 : p.agentflow;
  const vs = dflt === "v2" ? imp.data.agentflow_v2_vs_status_quo : imp.data.agentflow_vs_status_quo;
  const dfltKey: PolicyKey = dflt === "v2" ? "agentflow_v2" : "agentflow";
  const fc = met.data.metrics.forecast;
  const ra = met.data.metrics.risk_alerts;
  const an = met.data.metrics.anomaly;

  type Row = { label: string; key: keyof typeof sq; fmt: (x: number) => string; lower?: boolean; pp?: boolean; tip?: string };
  const fmtN = (x: number) => num(x);
  const rows: Row[] = [
    { label: "Unmet cash demand", key: "unmet_cash_demand_bdt", fmt: bdt },
    { label: "Liquidity shortage events (agent-hours)", key: "shortage_events", fmt: fmtN },
    { label: "Service availability", key: "service_availability_pct", fmt: (x) => pct(x, 2), lower: false, pp: true },
    { label: "Cash-out demand fill rate", key: "demand_fill_rate_pct", fmt: (x) => pct(x, 2), lower: false, pp: true },
    { label: "Agents with ≥1 shortage", key: "agents_with_shortage", fmt: fmtN },
  ];
  const opRows: Row[] = [
    { label: "Simulated transfers", key: "interventions", fmt: fmtN },
    { label: "Total rebalanced", key: "total_rebalanced_bdt", fmt: bdtCompact },
    { label: "Unnecessary transfers (false alerts)", key: "unnecessary_interventions_pct", fmt: (x) => pct(x, 1) },
    { label: "Donor shortage events within 6h of giving", key: "donor_shortage_events_after_transfer", fmt: fmtN },
    { label: "Estimated logistics cost", key: "estimated_logistics_cost_bdt", fmt: bdt },
    { label: "Need escalated to distributor (summed over decisions)", key: "escalated_need_bdt", fmt: bdtCompact },
    { label: "Unmet demand avoided per transfer", key: "unmet_avoided_per_transfer_bdt", fmt: bdt, lower: false },
    { label: "Unmet demand avoided per BDT 1,000 cost", key: "unmet_avoided_per_1000_cost_bdt", fmt: bdt, lower: false },
    { label: "Shortage events avoided per 100 transfers", key: "shortage_events_avoided_per_100_transfers", fmt: (x) => num(x, 1), lower: false },
  ];
  const cell = (k: PolicyKey, r: Row) => {
    const v = p[k][r.key];
    return v === undefined || v === null ? "—" : r.fmt(v as number);
  };

  return (
    <>
      <PageHeader
        title="Impact & Model Health"
        subtitle={`${imp.data.label}: every number below is computed by replaying the 14-day held-out period (${imp.data.period.start.slice(0, 10)} → ${imp.data.period.end.slice(0, 10)}, ${imp.data.period.agents} agents, never seen in training) with identical customer demand under each policy.`}
        right={<SourceTag kind="sim" />}
      />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <Card className="p-4 md:col-span-1">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Shortage events avoided</div>
          <div className="num mt-1 text-3xl font-semibold text-emerald-600">−{vs.shortage_events_reduction_pct.toFixed(1)}%</div>
          <div className="text-xs text-slate-500">
            {num(sq.shortage_events)} → {num(af.shortage_events)} agent-hours
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Unmet cash demand avoided</div>
          <div className="num mt-1 text-3xl font-semibold text-emerald-600">{bdtCompact(vs.unmet_demand_avoided_bdt)}</div>
          <div className="text-xs text-slate-500">−{vs.unmet_demand_reduction_pct.toFixed(1)}% vs. without AgentFlow</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Service availability</div>
          <div className="num mt-1 text-3xl font-semibold text-blue-700">{pct(af.service_availability_pct, 2)}</div>
          <div className="text-xs text-slate-500">
            +{vs.service_availability_gain_pp.toFixed(2)} pp (from {pct(sq.service_availability_pct, 2)})
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Extra cash injected</div>
          <div className="num mt-1 text-3xl font-semibold text-slate-900">BDT 0</div>
          <div className="text-xs text-slate-500">peer rebalancing only — {num(af.interventions)} simulated transfers (policy {dflt.toUpperCase()})</div>
        </Card>
      </div>

      <V1V2Glance v1={p.agentflow} v2={p.agentflow_v2} />

      <Card className="mt-4">
        <CardHeader
          title="Policy comparison"
          subtitle={`Same demand, same total cash. "Naive forecast" = same risk + rebalancing engine (V1) fed by a seasonal baseline forecast. V2 balances recipient benefit, donor safety and logistics cost. Default policy: ${dflt.toUpperCase()} (pre-registered decision rule).`}
        />
        <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Metric</th>
                {COLS.map((c) => (
                  <th key={c.key} className={cx("px-4 py-2 text-right font-medium", c.key === dfltKey && "text-slate-900")}>
                    {c.label}
                    {c.key === dfltKey && " (default)"}
                  </th>
                ))}
                <th className="px-4 py-2 text-right font-medium">Default vs. without</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="px-4 py-2.5 text-slate-700" title={imp.data!.metric_definitions[r.key]}>
                    {r.label}
                  </td>
                  {COLS.map((c) => (
                    <td key={c.key} className={cx("num px-4 py-2.5 text-right", c.key === dfltKey && "font-semibold")}>
                      {cell(c.key, r)}
                    </td>
                  ))}
                  <td className="px-4 py-2.5 text-right">
                    <Delta before={sq[r.key] as number} after={af[r.key] as number} lowerIsBetter={r.lower !== false} unit={r.pp ? "pp" : "%"} />
                  </td>
                </tr>
              ))}
              <tr className="bg-slate-50">
                <td colSpan={COLS.length + 2} className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Operations, safety & efficiency
                </td>
              </tr>
              {opRows.map((r) => (
                <tr key={r.key}>
                  <td className="px-4 py-2.5 text-slate-700" title={imp.data!.metric_definitions[r.key]}>
                    {r.label}
                  </td>
                  {COLS.map((c) => (
                    <td key={c.key} className={cx("num px-4 py-2.5 text-right", c.key === dfltKey && "font-semibold")}>
                      {c.key === "status_quo" ? "—" : cell(c.key, r)}
                    </td>
                  ))}
                  <td />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
          Hover a metric for its definition. V2 parameters were selected on training-period validation folds only; the held-out period was used once.
          Trade-off: V2 makes far fewer transfers, but a slightly higher share of them turn out unnecessary ({pct(p.agentflow_v2.unnecessary_interventions_pct, 1)} vs.{" "}
          {pct(p.agentflow.unnecessary_interventions_pct, 1)}). Assumptions: decisions at 09/11/13/15/17/19h, 1-hour transfer delay, same-district donors within 15 km, unusual-activity agents held for manual review.
        </p>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Daily unmet cash demand — held-out period" subtitle="Synthetic held-out simulation" />
          <div className="p-3">
            <DailyImpactChart data={imp.data.daily} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Impact by operational group" subtitle="Unmet cash demand by location cluster (consistency check)" />
          <div className="p-3">
            <CompareBars
              data={Object.entries(imp.data.groups.location_cluster).map(([g, v]) => ({
                name: titleCase(g),
                without: v.status_quo.unmet_cash_demand_bdt,
                with: v[dfltKey].unmet_cash_demand_bdt,
              }))}
              bars={[
                { key: "without", name: "Without AgentFlow", color: "#cbd5e1" },
                { key: "with", name: `With AgentFlow (${dflt.toUpperCase()})`, color: "#1d4ed8" },
              ]}
            />
          </div>
        </Card>
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold tracking-tight">Model health</h2>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Forecast accuracy: naive baselines vs. ML" subtitle={`Held-out ${fc.test_start.slice(0, 10)} → ${fc.test_end.slice(0, 10)} · ${num(fc.n_test_rows)} agent-hours`} right={<SourceTag kind="model" />} />
          <div className="overflow-x-auto">
            <table className="w-full whitespace-nowrap text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Target (next 6h)</th>
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">MAE</th>
                  <th className="px-4 py-2 text-right font-medium">RMSE</th>
                  <th className="px-4 py-2 text-right font-medium">WAPE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(fc.targets).map(([name, t]) => (
                  <Fragment key={name}>
                    {Object.entries(t.baselines).map(([b, m]) => (
                      <tr key={name + b}>
                        <td className="px-4 py-2 text-slate-600">{name === "cash_demand" ? "Cash-out demand" : "Peak requirement"}</td>
                        <td className="px-4 py-2 text-slate-600">{b === "naive_yesterday" ? "Naive (yesterday)" : "Seasonal 7-day avg"}</td>
                        <td className="num px-4 py-2 text-right">{bdt(m.mae)}</td>
                        <td className="num px-4 py-2 text-right">{bdt(m.rmse)}</td>
                        <td className="num px-4 py-2 text-right">{pct(100 * m.wape, 1)}</td>
                      </tr>
                    ))}
                    <tr className="bg-blue-50/40">
                      <td className="px-4 py-2 font-medium">{name === "cash_demand" ? "Cash-out demand" : "Peak requirement"}</td>
                      <td className="px-4 py-2 font-medium">
                        ML (gradient boosting)
                        <span className="block text-xs font-normal text-emerald-700">−{t.improvement_vs_best_baseline.mae_pct.toFixed(1)}% MAE vs best baseline</span>
                      </td>
                      <td className="num px-4 py-2 text-right font-semibold">{bdt(t.ml_model.mae)}</td>
                      <td className="num px-4 py-2 text-right font-semibold">{bdt(t.ml_model.rmse)}</td>
                      <td className="num px-4 py-2 text-right font-semibold">{pct(100 * t.ml_model.wape, 1)}</td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
            P90 quantile model: empirical coverage {pct(100 * fc.quantile_p90.empirical_coverage, 1)} (nominal 90%). Time-based split with 6h purge; no shuffling.
          </p>
        </Card>
        <Card>
          <CardHeader title="Top forecast drivers" subtitle="Permutation importance (MAE increase when feature is shuffled), cash-demand model, held-out" />
          <div className="p-3">
            <CompareBars
              layout="vertical"
              height={300}
              data={fc.feature_importance_cash_demand.slice(0, 10).map((f) => ({ name: f.feature, value: f.mae_increase }))}
              bars={[{ key: "value", name: "MAE increase (BDT)", color: "#1d4ed8" }]}
            />
          </div>
        </Card>
        <Card>
          <CardHeader title="Risk engine as early warning" subtitle={`Does a HIGH/CRITICAL alert anticipate a real shortage in the next 6h? ${num(ra.n_decisions)} held-out decisions, ${pct(100 * ra.shortage_prevalence, 1)} shortage prevalence`} right={<SourceTag kind="calc" />} />
          <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Risk engine fed by</th>
                <th className="px-4 py-2 text-right font-medium">Precision</th>
                <th className="px-4 py-2 text-right font-medium">Recall</th>
                <th className="px-4 py-2 text-right font-medium">ROC-AUC</th>
                <th className="px-4 py-2 text-right font-medium">Alert rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(ra.variants).map(([k, v]) => (
                <tr key={k} className={k === "ml_forecast" ? "bg-blue-50/40 font-medium" : ""}>
                  <td className="px-4 py-2">{k === "ml_forecast" ? "ML forecast" : "Naive seasonal forecast"}</td>
                  <td className="num px-4 py-2 text-right">{pct(100 * v.precision, 1)}</td>
                  <td className="num px-4 py-2 text-right">{pct(100 * v.recall, 1)}</td>
                  <td className="num px-4 py-2 text-right">{v.roc_auc.toFixed(3)}</td>
                  <td className="num px-4 py-2 text-right">{pct(100 * v.alert_rate, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div className="grid grid-cols-4 gap-2 border-t border-slate-100 p-4 text-center text-xs">
            {Object.entries(ra.calibration_by_level).map(([lvl, c]) => (
              <div key={lvl} className="rounded-md bg-slate-50 p-2">
                <div className="font-semibold text-slate-700">{lvl}</div>
                <div className="num text-base font-semibold">{c.observed_shortage_rate === null ? "—" : pct(100 * c.observed_shortage_rate, 0)}</div>
                <div className="text-slate-500">observed shortage rate</div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Behavioural anomaly detection" subtitle={`Against ${an.n_labelled_anomalies} injected (labelled) anomalous agent-hours in the held-out period`} right={<SourceTag kind="model" />} />
          <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Detector</th>
                <th className="px-4 py-2 text-right font-medium">ROC-AUC</th>
                <th className="px-4 py-2 text-right font-medium">Average precision</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(an.components).map(([k, v]) => (
                <tr key={k} className={k === "hybrid" ? "bg-blue-50/40 font-medium" : ""}>
                  <td className="px-4 py-2">{k === "iforest" ? "Isolation Forest only" : k === "rule" ? "Robust deviation rule only" : "Hybrid (deployed)"}</td>
                  <td className="num px-4 py-2 text-right">{v.roc_auc.toFixed(3)}</td>
                  <td className="num px-4 py-2 text-right">{v.average_precision.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-slate-100 p-4 text-xs text-slate-600">
            {Object.entries(an.by_status).map(([k, v]) => (
              <div key={k} className="rounded-md bg-slate-50 p-2">
                <div className="font-semibold">{k === "ANOMALOUS" ? "Unusual-activity flag" : "Watch or higher"}</div>
                Precision {pct(100 * v.precision, 1)} · Recall {pct(100 * v.recall, 1)}
              </div>
            ))}
            <div className="col-span-2">
              Recall by injected type (watch+):{" "}
              {Object.entries(an.recall_by_type_watch_or_higher)
                .map(([t, r]) => `${titleCase(t)} ${pct(100 * r, 0)}`)
                .join(" · ")}
              . Large-ticket episodes are hardest to detect at hourly granularity.
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="Fairness & consistency across operational groups" subtitle="No personal attributes exist in the data; groups are synthetic location clusters and volume segments." />
        <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
          {(["location_cluster", "agent_volume_segment"] as const).map((g) => (
            <div key={g} className="overflow-x-auto">
            <table className="w-full whitespace-nowrap text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="pb-1 font-medium">{g === "location_cluster" ? "Location cluster" : "Volume segment"}</th>
                  <th className="pb-1 text-right font-medium">Forecast WAPE (ML / naive)</th>
                  <th className="pb-1 text-right font-medium">Alert recall</th>
                  <th className="pb-1 text-right font-medium">Alert precision</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(fc.group_consistency[g]).map(([k, v]) => {
                  const a = ra.group_consistency[g][k];
                  return (
                    <tr key={k}>
                      <td className="py-1.5">{titleCase(k)}</td>
                      <td className="num py-1.5 text-right">
                        {pct(100 * v.ml_wape, 1)} / {pct(100 * v.naive_wape, 1)}
                      </td>
                      <td className="num py-1.5 text-right">{pct(100 * a.recall, 1)}</td>
                      <td className="num py-1.5 text-right">{pct(100 * a.precision, 1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          ))}
        </div>
        <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
          Forecast error is consistent across groups (WAPE within a few points). Alert recall is lower for urban-core agents, where shortages are rare (≈1.4% prevalence) — documented in docs/EVALUATION.md.
        </p>
      </Card>
      <MorningPlanResearch />
    </>
  );
}

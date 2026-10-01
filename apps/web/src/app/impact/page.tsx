"use client";

import { Fragment } from "react";
import { useApi } from "@/lib/api";
import { bdt, bdtCompact, num, pct, titleCase } from "@/lib/format";
import type { ImpactResponse, MetricsResponse } from "@/lib/types";
import { CompareBars, DailyImpactChart } from "@/components/charts";
import { Card, CardHeader, ErrorState, Loading, PageHeader, SourceTag, cx } from "@/components/ui";

const POLICY_LABEL = {
  status_quo: "Without AgentFlow",
  naive_rebalancing: "Rebalancing with naive forecast",
  agentflow: "With AgentFlow (ML)",
} as const;

function Delta({ before, after, lowerIsBetter = true, unit = "%" }: { before: number; after: number; lowerIsBetter?: boolean; unit?: string }) {
  const d = unit === "pp" ? after - before : before ? (100 * (after - before)) / before : 0;
  const good = lowerIsBetter ? d < 0 : d > 0;
  const tone = Math.abs(d) < 0.05 ? "text-slate-500" : good ? "text-emerald-600" : "text-red-600";
  return <span className={cx("num text-xs font-semibold", tone)}>{`${d > 0 ? "+" : ""}${d.toFixed(1)}${unit === "pp" ? " pp" : "%"}`}</span>;
}

export default function ImpactPage() {
  const imp = useApi<ImpactResponse>("/api/impact");
  const met = useApi<MetricsResponse>("/api/model/metrics");
  if (imp.error || met.error) return <ErrorState message={(imp.error || met.error) as string} onRetry={() => { imp.reload(); met.reload(); }} />;
  if (!imp.data || !met.data) return <Loading />;
  const p = imp.data.policies;
  const sq = p.status_quo;
  const af = p.agentflow;
  const nv = p.naive_rebalancing;
  const fc = met.data.metrics.forecast;
  const ra = met.data.metrics.risk_alerts;
  const an = met.data.metrics.anomaly;

  const rows: { label: string; key: keyof typeof sq; fmt: (x: number) => string; lower?: boolean; pp?: boolean }[] = [
    { label: "Liquidity shortage events (agent-hours)", key: "shortage_events", fmt: (x) => num(x) },
    { label: "Unmet cash demand", key: "unmet_cash_demand_bdt", fmt: bdt },
    { label: "Agents with ≥1 shortage", key: "agents_with_shortage", fmt: (x) => num(x) },
    { label: "Service availability", key: "service_availability_pct", fmt: (x) => pct(x, 2), lower: false, pp: true },
    { label: "Cash-out demand fill rate", key: "demand_fill_rate_pct", fmt: (x) => pct(x, 2), lower: false, pp: true },
  ];

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
          <div className="num mt-1 text-3xl font-semibold text-emerald-600">−{imp.data.agentflow_vs_status_quo.shortage_events_reduction_pct.toFixed(1)}%</div>
          <div className="text-xs text-slate-500">
            {num(sq.shortage_events)} → {num(af.shortage_events)} agent-hours
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Unmet cash demand avoided</div>
          <div className="num mt-1 text-3xl font-semibold text-emerald-600">{bdtCompact(imp.data.agentflow_vs_status_quo.unmet_demand_avoided_bdt)}</div>
          <div className="text-xs text-slate-500">−{imp.data.agentflow_vs_status_quo.unmet_demand_reduction_pct.toFixed(1)}% vs. without AgentFlow</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Service availability</div>
          <div className="num mt-1 text-3xl font-semibold text-blue-700">{pct(af.service_availability_pct, 2)}</div>
          <div className="text-xs text-slate-500">
            +{imp.data.agentflow_vs_status_quo.service_availability_gain_pp.toFixed(2)} pp (from {pct(sq.service_availability_pct, 2)})
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Extra cash injected</div>
          <div className="num mt-1 text-3xl font-semibold text-slate-900">BDT 0</div>
          <div className="text-xs text-slate-500">peer rebalancing only — {num(af.interventions)} simulated transfers</div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="Without AgentFlow vs. With AgentFlow" subtitle="Same demand, same total cash. The middle column isolates the value of the ML forecast: same risk + rebalancing engine fed by a naive seasonal forecast." />
        <div className="overflow-x-auto">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Metric</th>
                <th className="px-4 py-2 text-right font-medium">{POLICY_LABEL.status_quo}</th>
                <th className="px-4 py-2 text-right font-medium">{POLICY_LABEL.naive_rebalancing}</th>
                <th className="px-4 py-2 text-right font-medium">{POLICY_LABEL.agentflow}</th>
                <th className="px-4 py-2 text-right font-medium">AgentFlow vs. without</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="px-4 py-2.5 text-slate-700" title={imp.data!.metric_definitions[r.key]}>
                    {r.label}
                  </td>
                  <td className="num px-4 py-2.5 text-right">{r.fmt(sq[r.key] as number)}</td>
                  <td className="num px-4 py-2.5 text-right">{r.fmt(nv[r.key] as number)}</td>
                  <td className="num px-4 py-2.5 text-right font-semibold">{r.fmt(af[r.key] as number)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Delta before={sq[r.key] as number} after={af[r.key] as number} lowerIsBetter={r.lower !== false} unit={r.pp ? "pp" : "%"} />
                  </td>
                </tr>
              ))}
              <tr>
                <td className="px-4 py-2.5 text-slate-700">Simulated transfers / total moved</td>
                <td className="num px-4 py-2.5 text-right">—</td>
                <td className="num px-4 py-2.5 text-right">
                  {nv.interventions} / {bdtCompact(nv.total_rebalanced_bdt)}
                </td>
                <td className="num px-4 py-2.5 text-right font-semibold">
                  {af.interventions} / {bdtCompact(af.total_rebalanced_bdt)}
                </td>
                <td />
              </tr>
              <tr>
                <td className="px-4 py-2.5 text-slate-700" title={imp.data.metric_definitions.unnecessary_interventions_pct}>
                  Unnecessary transfers (false alerts)
                </td>
                <td className="num px-4 py-2.5 text-right">—</td>
                <td className="num px-4 py-2.5 text-right">{pct(nv.unnecessary_interventions_pct, 1)}</td>
                <td className="num px-4 py-2.5 text-right font-semibold">{pct(af.unnecessary_interventions_pct, 1)}</td>
                <td />
              </tr>
              <tr>
                <td className="px-4 py-2.5 text-slate-700" title={imp.data.metric_definitions.donor_shortage_events_after_transfer}>
                  Donor shortage events within 6h of giving
                </td>
                <td className="num px-4 py-2.5 text-right">—</td>
                <td className="num px-4 py-2.5 text-right">{num(nv.donor_shortage_events_after_transfer)}</td>
                <td className="num px-4 py-2.5 text-right font-semibold">{num(af.donor_shortage_events_after_transfer)}</td>
                <td />
              </tr>
              <tr>
                <td className="px-4 py-2.5 text-slate-700">Estimated logistics cost</td>
                <td className="num px-4 py-2.5 text-right">—</td>
                <td className="num px-4 py-2.5 text-right">{bdt(nv.estimated_logistics_cost_bdt)}</td>
                <td className="num px-4 py-2.5 text-right font-semibold">{bdt(af.estimated_logistics_cost_bdt)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
        <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
          Hover a metric for its definition. Assumptions: decisions at 09/11/13/15/17/19h, 1-hour transfer delay, same-district donors within 15 km keeping ≥110% of their own P90 requirement, unusual-activity agents held for manual review.
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
                with: v.agentflow.unmet_cash_demand_bdt,
              }))}
              bars={[
                { key: "without", name: "Without AgentFlow", color: "#cbd5e1" },
                { key: "with", name: "With AgentFlow", color: "#1d4ed8" },
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
            <table key={g} className="w-full whitespace-nowrap text-sm">
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
          ))}
        </div>
        <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
          Forecast error is consistent across groups (WAPE within a few points). Alert recall is lower for urban-core agents, where shortages are rare (≈1.4% prevalence) — documented in docs/EVALUATION.md.
        </p>
      </Card>
    </>
  );
}

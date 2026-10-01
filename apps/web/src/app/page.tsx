"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, bdtCompact, dateTime, pct, ratioPct, titleCase } from "@/lib/format";
import type { Overview } from "@/lib/types";
import { NetworkTrendChart, RiskDistributionChart } from "@/components/charts";
import { AnomalyBadge, Card, CardHeader, ErrorState, Kpi, Loading, PageHeader, RiskBadge, SourceTag } from "@/components/ui";

export default function CommandCenter() {
  const { asOf } = useAsOf();
  const { data, error, loading, reload } = useApi<Overview>(asOf ? "/api/overview" : null, { as_of: asOf });

  return (
    <>
      <PageHeader
        title="Command Center"
        subtitle="AgentFlow predicts where an MFS agent may run short of liquidity before customers are affected, explains why, and recommends a safe, human-reviewed rebalancing action."
        right={data && <span className="text-xs text-slate-500">Snapshot: {dateTime(data.as_of)} · next {data.horizon_hours}h horizon</span>}
      />
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Loading />}
      {data && (
        <div className={loading ? "opacity-60 transition-opacity" : ""}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Active agents" value={data.kpis.active_agents} sub={`${data.kpis.anomaly_watch_agents} with unusual activity`} />
            <Kpi label="At-risk agents" value={data.kpis.at_risk_agents} tone="warn" sub={`${data.kpis.medium_risk_agents} more at MEDIUM`} tip={data.kpi_definitions.at_risk_agents} />
            <Kpi label="Critical agents" value={data.kpis.critical_agents} tone="danger" sub="risk score ≥ 75" />
            <Kpi
              label="Projected service readiness"
              value={pct(data.kpis.projected_service_availability_pct, 1)}
              tone="brand"
              sub={<>→ {pct(data.kpis.projected_service_availability_after_plan_pct, 1)} with recommended plan</>}
              tip={data.kpi_definitions.projected_service_availability_pct}
            />
            <Kpi label="Forecast 6h cash demand" value={bdtCompact(data.kpis.forecast_cash_demand_6h)} sub={`Expected shortfall ${bdtCompact(data.kpis.total_expected_shortfall)}`} tip={data.kpi_definitions.forecast_cash_demand_6h} />
            <Kpi label="Recommended rebalancing" value={bdtCompact(data.kpis.recommended_rebalancing_value)} tone="good" sub={`${data.kpis.n_recommendations} transfers · ${bdtCompact(data.kpis.escalated_amount)} escalated`} />
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

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
            <Card className="xl:col-span-3">
              <CardHeader
                title="Top at-risk agents"
                subtitle="Ranked by liquidity risk score"
                right={
                  <Link href="/agents" className="flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline">
                    All agents <ArrowRight className="h-3 w-3" />
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
                      <tr key={a.agent_id} className="hover:bg-slate-50">
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
            <Card className="xl:col-span-2">
              <CardHeader
                title="Urgent rebalancing recommendations"
                subtitle="Peer transfers awaiting human review"
                right={
                  <Link href="/rebalancing" className="flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline">
                    Review <ArrowRight className="h-3 w-3" />
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
                    <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      <span>{r.district}</span>·<span>{r.distance_km.toFixed(1)} km</span>·
                      <RiskBadge level={r.destination_risk_before.risk_level} score={r.destination_risk_before.risk_score} />
                      <ArrowRight className="h-3 w-3" />
                      <RiskBadge level={r.destination_risk_after.risk_level} score={r.destination_risk_after.risk_score} />
                    </div>
                  </li>
                ))}
              </ul>
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
          <p className="mt-4 text-xs text-slate-400">{data.data_label}</p>
        </div>
      )}
    </>
  );
}

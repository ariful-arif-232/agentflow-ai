"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Eye, Truck } from "lucide-react";
import { useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, dateTime, num, ratioPct, titleCase } from "@/lib/format";
import type { AgentDetail } from "@/lib/types";
import { AgentHistoryChart } from "@/components/charts";
import { AnomalyBadge, Card, CardHeader, ErrorState, Loading, RISK_STYLE, RiskBadge, ScoreBar, SourceTag, cx } from "@/components/ui";

const COMPONENT_LABEL: Record<string, string> = {
  coverage: "Reserve coverage vs. forecast",
  tail_risk: "High-demand (P90) scenario gap",
  deficit_size: "Size of expected shortfall",
  velocity: "Recent transaction velocity",
  history: "Historical shortage frequency",
};

const ACTION_ICON: Record<string, React.ReactNode> = {
  RECEIVE_REBALANCING: <Truck className="h-5 w-5 text-teal-700" />,
  ESCALATE: <AlertTriangle className="h-5 w-5 text-orange-600" />,
  MANUAL_REVIEW: <Eye className="h-5 w-5 text-fuchsia-700" />,
  DONOR: <ArrowRight className="h-5 w-5 text-teal-700" />,
  MONITOR: <Eye className="h-5 w-5 text-amber-600" />,
  NONE: <CheckCircle2 className="h-5 w-5 text-emerald-600" />,
};

function Tile({ label, value, sub, tag, tone }: { label: string; value: string; sub?: string; tag?: React.ReactNode; tone?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center justify-between gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
        {tag}
      </div>
      <div className={cx("num mt-1.5 text-xl font-semibold", tone || "text-slate-900")}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { asOf } = useAsOf();
  const { data, error, loading, reload } = useApi<AgentDetail>(asOf && id ? `/api/agents/${encodeURIComponent(id)}` : null, { as_of: asOf });

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Loading label="Loading agent intelligence…" />;
  const r = data.risk;
  const f = data.forecast;
  const shortfall = f.expected_shortfall > 0;
  const recs = data.recommendations.as_destination;
  const reasons = data.explanation.filter((e) => e.component !== "context");
  const context = data.explanation.filter((e) => e.component === "context");

  return (
    <div className={loading ? "opacity-60" : ""}>
      <Link href="/agents" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-3 w-3" /> All agents
      </Link>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">Agent {data.agent.agent_id}</h1>
            <RiskBadge level={r.risk_level} score={r.risk_score} />
            <AnomalyBadge status={data.anomaly.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {data.agent.district} · {titleCase(data.agent.location_cluster)} · {titleCase(data.agent.agent_type)} · {titleCase(data.agent.agent_volume_segment)} volume · as of {dateTime(data.as_of)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Current cash" value={bdt(data.liquidity.cash_balance)} sub={`Morning drawer target ${bdt(data.liquidity.morning_target_cash)}`} tag={<SourceTag kind="data" />} />
        <Tile label="Next-6h cash-out demand" value={bdt(f.pred_cash_demand_6h)} sub={`Same window, 7-day avg: ${bdt(f.seasonal_same_window_avg7)}`} tag={<SourceTag kind="model" />} />
        <Tile label="Next-6h peak cash requirement" value={bdt(f.pred_net_requirement_6h)} sub={`P90 scenario: ${bdt(f.pred_net_requirement_p90_6h)}`} tag={<SourceTag kind="model" />} />
        <Tile
          label={shortfall ? "Expected shortfall" : "Surplus above P90"}
          value={shortfall ? bdt(f.expected_shortfall) : bdt(f.expected_surplus)}
          sub={`Coverage ${ratioPct(r.coverage_ratio)} of forecast requirement`}
          tone={shortfall ? "text-red-600" : "text-emerald-700"}
          tag={<SourceTag kind="calc" />}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader title="Why this risk?" subtitle="Every statement below is generated from calculated values — forecasts, balances and agent history." right={<SourceTag kind="calc" />} />
          <div className="grid grid-cols-1 gap-6 p-5 md:grid-cols-5">
            <div className="md:col-span-2">
              <div className="flex items-end gap-2">
                <span className="num text-5xl font-semibold" style={{ color: RISK_STYLE[r.risk_level].fill }}>
                  {r.risk_score.toFixed(0)}
                </span>
                <span className="mb-1.5 text-sm text-slate-500">/ 100 · {r.risk_level}</span>
              </div>
              <div className="mt-4 space-y-3">
                {Object.entries(r.components).map(([k, v]) => (
                  <div key={k}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="text-slate-600">{COMPONENT_LABEL[k] || k}</span>
                      <span className="num text-slate-900">
                        {num(v, 1)} <span className="text-slate-400">/ {r.component_max[k]}</span>
                      </span>
                    </div>
                    <ScoreBar value={v} max={r.component_max[k]} color={RISK_STYLE[r.risk_level].fill} />
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
                Risk score = sum of five bounded components. Forecast coverage and deficit dominate (up to 85 points). Behavioural anomalies do not change this score; they change review priority.
              </p>
            </div>
            <div className="md:col-span-3">
              <ol className="space-y-2.5">
                {reasons.map((e, i) => (
                  <li key={e.code} className="flex gap-3 text-sm">
                    <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-slate-900 text-[11px] font-semibold text-white">{i + 1}</span>
                    <span className="text-slate-800">{e.text}</span>
                  </li>
                ))}
              </ol>
              {context.length > 0 && (
                <div className="mt-4 rounded-lg bg-slate-50 p-3">
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Demand context</div>
                  <ul className="space-y-1.5 text-sm text-slate-700">
                    {context.map((e) => (
                      <li key={e.code}>• {e.text}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </Card>

        <div className="space-y-4 xl:col-span-2">
          <Card>
            <CardHeader title="Recommended action" subtitle="Decision support — requires human review" right={<SourceTag kind="rec" />} />
            <div className="p-5">
              <div className="flex gap-3">
                {ACTION_ICON[data.recommended_action.type]}
                <p className="text-sm text-slate-800">{data.recommended_action.summary}</p>
              </div>
              {recs.length > 0 && (
                <div className="mt-4 space-y-2">
                  {recs.map((x) => (
                    <div key={x.id} className="rounded-lg border border-slate-200 p-3 text-xs">
                      <div className="flex justify-between font-medium text-slate-900">
                        <span>
                          {x.id}: {x.source_agent} → {x.destination_agent}
                        </span>
                        <span className="num">{bdt(x.recommended_amount)}</span>
                      </div>
                      <div className="mt-1 text-slate-500">
                        {x.distance_km.toFixed(1)} km · donor keeps {bdt(x.source_cash_after)} (protected level {bdt(x.source_protected_level)})
                      </div>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 pt-1 text-xs">
                    <span className="text-slate-500">Estimated risk after plan:</span>
                    <RiskBadge level={recs[0].destination_risk_before.risk_level} score={recs[0].destination_risk_before.risk_score} />
                    <ArrowRight className="h-3 w-3 text-slate-400" />
                    <RiskBadge level={recs[0].destination_risk_after.risk_level} score={recs[0].destination_risk_after.risk_score} />
                  </div>
                  <Link href={`/rebalancing?focus=${data.agent.agent_id}`} className="mt-2 inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700">
                    Review recommendation <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              )}
            </div>
          </Card>
          <Card>
            <CardHeader title="Behavioural activity" subtitle="Unusual activity vs. this agent's own history (last 6h)" />
            <div className="p-5 text-sm">
              <div className="flex items-center gap-3">
                <AnomalyBadge status={data.anomaly.status} />
                <span className="num text-xs text-slate-500">
                  score {data.anomaly.score.toFixed(3)} · training-percentile scale; Watch ≥ 0.985, Unusual ≥ 0.995
                </span>
              </div>
              {data.anomaly.drivers.length > 0 && (
                <ul className="mt-3 space-y-1.5 text-slate-700">
                  {data.anomaly.drivers.map((d) => (
                    <li key={d.feature}>
                      • {titleCase(d.description)}
                      {d.ratio_vs_usual !== null && d.ratio_vs_usual > 1.05 && <span className="num font-medium"> — {d.ratio_vs_usual.toFixed(1)}× usual</span>}
                      {d.ratio_vs_usual === null && <span className="num font-medium"> — {d.robust_z.toFixed(1)} robust-z</span>}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-slate-500">{data.anomaly.note}</p>
            </div>
          </Card>
        </div>
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Last 72 hours"
          subtitle="Cash balance (manual 08:00 drawer reset visible), hourly cash-out demand, unmet demand and the forecast 6h peak requirement at each hour."
          right={<SourceTag kind="data" />}
        />
        <div className="p-3">
          <AgentHistoryChart data={data.history} />
        </div>
      </Card>

      <Card className="mt-4">
        <CardHeader title="Model & evidence context" subtitle="Synthetic held-out evaluation of the forecasting model used above" />
        <div className="grid grid-cols-2 gap-4 p-5 text-sm md:grid-cols-4">
          <div>
            <div className="text-xs text-slate-500">Cash-demand MAE (ML)</div>
            <div className="num font-semibold">{bdt(data.model_context.cash_demand_mae_ml)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Cash-demand MAE (naive baseline)</div>
            <div className="num font-semibold">{bdt(data.model_context.cash_demand_mae_naive)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Peak-requirement MAE (ML)</div>
            <div className="num font-semibold">{bdt(data.model_context.net_requirement_mae_ml)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">P90 band empirical coverage</div>
            <div className="num font-semibold">{data.model_context.p90_coverage ? `${(100 * data.model_context.p90_coverage).toFixed(1)}%` : "—"}</div>
          </div>
        </div>
      </Card>
    </div>
  );
}

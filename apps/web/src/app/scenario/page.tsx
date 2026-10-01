"use client";

import { useEffect, useState } from "react";
import { apiPost, useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdtCompact, pct } from "@/lib/format";
import type { AgentsResponse, RiskLevel, ScenarioResponse } from "@/lib/types";
import { Card, CardHeader, ErrorState, Loading, PageHeader, RISK_STYLE, SourceTag, cx } from "@/components/ui";

const SHOCKS = [0, 10, 25, 40];
const LEVELS: RiskLevel[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function Compare({ label, base, scen, fmt, higherIsWorse = true, neutral = false }: { label: string; base: number; scen: number; fmt: (x: number) => string; higherIsWorse?: boolean; neutral?: boolean }) {
  const worse = higherIsWorse ? scen > base : scen < base;
  const tone = neutral || scen === base ? "text-slate-900" : worse ? "text-red-600" : "text-emerald-600";
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cx("num mt-1.5 whitespace-nowrap text-2xl font-semibold", tone)}>{fmt(scen)}</div>
      <div className="num mt-0.5 whitespace-nowrap text-xs text-slate-500">current: {fmt(base)}</div>
    </Card>
  );
}

export default function ScenarioPage() {
  const { asOf } = useAsOf();
  const agents = useApi<AgentsResponse>(asOf ? "/api/agents" : null, { as_of: asOf, search: "AG-0001" });
  const [shock, setShock] = useState(25);
  const [district, setDistrict] = useState("");
  const [regional, setRegional] = useState(30);
  const [res, setRes] = useState<ScenarioResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!asOf) return;
    let cancelled = false;
    setBusy(true);
    apiPost<ScenarioResponse>("/api/scenario", { demand_shock_pct: shock, district: district || null, regional_shock_pct: district ? regional : 0, as_of: asOf })
      .then((r) => !cancelled && (setRes(r), setErr(null)))
      .catch((e) => !cancelled && setErr(e instanceof Error ? e.message : "Scenario failed"))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [asOf, shock, district, regional]);

  return (
    <>
      <PageHeader
        title="Scenario Lab"
        subtitle="Stress-test the network: scale the ML demand forecasts and let the same risk and rebalancing engines recompute everything. Results are calculated live, not pre-set."
        right={<SourceTag kind="sim" />}
      />
      <Card className="mb-4 p-5">
        <div className="flex flex-wrap items-end gap-8">
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Network cash-out demand shock</div>
            <div className="flex gap-1.5">
              {SHOCKS.map((s) => (
                <button key={s} onClick={() => setShock(s)} className={cx("num rounded-md px-3 py-1.5 text-sm ring-1 ring-inset", shock === s ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50")}>
                  {s === 0 ? "None" : `+${s}%`}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Regional spike (e.g. local event, festival)</div>
            <div className="flex items-center gap-2">
              <select aria-label="District" className="rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={district} onChange={(e) => setDistrict(e.target.value)}>
                <option value="">No regional spike</option>
                {agents.data?.filters.districts.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
              {district && (
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  <input type="range" min={0} max={100} step={5} value={regional} onChange={(e) => setRegional(Number(e.target.value))} />
                  <span className="num w-12">+{regional}%</span>
                </label>
              )}
            </div>
          </div>
          {busy && <span className="text-xs text-slate-500">Recomputing…</span>}
        </div>
      </Card>
      {err && <ErrorState message={err} />}
      {!res && !err && <Loading />}
      {res && (
        <div className={busy ? "opacity-60" : ""}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Compare label="At-risk agents" base={res.baseline.at_risk_agents} scen={res.scenario.at_risk_agents} fmt={(x) => String(x)} />
            <Compare label="Expected shortfall (6h)" base={res.baseline.total_expected_shortfall} scen={res.scenario.total_expected_shortfall} fmt={bdtCompact} />
            <Compare label="Service readiness" base={res.baseline.projected_service_availability_pct} scen={res.scenario.projected_service_availability_pct} fmt={(x) => pct(x, 1)} higherIsWorse={false} />
            <Compare label="Recommended rebalancing" base={res.baseline.recommended_rebalancing_value} scen={res.scenario.recommended_rebalancing_value} fmt={bdtCompact} neutral />
            <Compare label="Escalated to distributor" base={res.baseline.escalated_amount} scen={res.scenario.escalated_amount} fmt={bdtCompact} />
          </div>
          <Card className="mt-4">
            <CardHeader title="Risk distribution: current vs. scenario" subtitle={res.note} right={<SourceTag kind="calc" />} />
            <div className="space-y-4 p-5">
              {(["baseline", "scenario"] as const).map((k) => {
                const d = res[k].risk_distribution;
                const total = LEVELS.reduce((a, l) => a + d[l], 0) || 1;
                return (
                  <div key={k}>
                    <div className="mb-1 text-xs font-medium text-slate-600">{k === "baseline" ? "Current forecast" : "Scenario"}</div>
                    <div className="flex h-8 overflow-hidden rounded-md">
                      {LEVELS.map((l) => (
                        <div key={l} className="flex items-center justify-center text-[11px] font-semibold text-white" style={{ width: `${(100 * d[l]) / total}%`, backgroundColor: RISK_STYLE[l].fill }} title={`${l}: ${d[l]}`}>
                          {d[l] / total > 0.09 ? `${l} ${d[l]}` : d[l] || ""}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
          <p className="mt-3 text-xs text-slate-500">
            Peer rebalancing redistributes existing cash; as stress grows, more need must be escalated to distributor replenishment — the scenario shows when that tipping point arrives.
          </p>
        </div>
      )}
    </>
  );
}

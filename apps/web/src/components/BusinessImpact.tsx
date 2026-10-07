import { ArrowRight, FlaskConical } from "lucide-react";
import { bdt, bdtCompact, num, pct } from "@/lib/format";
import type { BusinessImpact } from "@/lib/types";
import { Card, CardHeader, SourceTag, cx } from "@/components/ui";

/** Signed compact BDT: "−BDT 1.9 lakh" rather than "BDT -1.9 lakh". */
function signedBdt(x: number | null | undefined, compact = false): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const s = compact ? bdtCompact(Math.abs(x)) : bdt(Math.abs(x));
  return x < 0 ? `−${s}` : s;
}

/** Short signed BDT for the sensitivity grid (currency in the caption): "−1.9 lakh", "−94,712". */
function shortSigned(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const a = Math.abs(x);
  const s = a >= 1e5 ? `${(a / 1e5).toFixed(1)} lakh` : num(a);
  return x < 0 ? `−${s}` : s;
}

export const BIZ_LABEL = "Synthetic simulated estimate — not measured upay performance.";

function EstimateTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900 ring-1 ring-inset ring-amber-600/30">
      <FlaskConical className="h-3 w-3" aria-hidden /> Simulated estimate
    </span>
  );
}

function Step({ eyebrow, value, sub, tag }: { eyebrow: string; value: string; sub: string; tag?: React.ReactNode }) {
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex min-h-[1.25rem] flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{eyebrow}</span>
        {tag}
      </div>
      <div className="num mt-1 text-lg font-semibold text-slate-900">{value}</div>
      <div className="text-xs leading-snug text-slate-600">{sub}</div>
    </div>
  );
}

/** Business Impact — Synthetic Simulation (Phase-2, additive to the Phase-1 evidence above). */
export function BusinessImpactCard({ biz }: { biz: BusinessImpact }) {
  const c = biz.calculations;
  const sq = c.policies.status_quo.customer;
  const v1 = c.vs_status_quo.agentflow_v1;
  const v2 = c.vs_status_quo.agentflow_v2;
  const p1 = c.policies.agentflow_v1.operations;
  const p2 = c.policies.agentflow_v2.operations;
  const e1 = v1.economics.peer_transfers_only;
  const e2 = v2.economics.peer_transfers_only;
  const bps = biz.assumptions.agent_commission_bps;
  const [lo, hi] = v2.customer.estimated_transactions_protected_range;
  const sens = biz.sensitivity.agentflow_v2;
  const rates = Array.from(new Set(sens.grid.map((g) => g.agent_commission_bps)));
  const mults = Array.from(new Set(sens.grid.map((g) => g.cost_multiplier)));
  const cell = (m: number, r: number) => sens.grid.find((g) => g.cost_multiplier === m && g.agent_commission_bps === r);

  const rows: { label: string; a: string; b: string; est?: boolean }[] = [
    {
      label: "Cash-out value protected vs status quo",
      a: bdtCompact(v1.customer.cash_out_value_protected_bdt),
      b: bdtCompact(v2.customer.cash_out_value_protected_bdt),
    },
    {
      label: "Est. cash-out transactions protected",
      a: num(v1.customer.estimated_transactions_protected),
      b: num(v2.customer.estimated_transactions_protected),
      est: true,
    },
    {
      label: `Illustrative agent commission protected (${bps} bps)`,
      a: bdt(v1.agent.illustrative_commission_protected_bdt),
      b: bdt(v2.agent.illustrative_commission_protected_bdt),
      est: true,
    },
    {
      label: "Peer transfers · cost per transfer",
      a: `${num(p1.peer_transfers)} · ${bdt(p1.average_cost_per_peer_transfer_bdt)}`,
      b: `${num(p2.peer_transfers)} · ${bdt(p2.average_cost_per_peer_transfer_bdt)}`,
    },
    {
      label: "Peer logistics cost proxy",
      a: bdtCompact(p1.peer_logistics_cost_bdt),
      b: bdtCompact(p2.peer_logistics_cost_bdt),
      est: true,
    },
    {
      label: "Distributor workload (escalated agent-days)",
      a: num(p1.escalated_agent_days),
      b: num(p2.escalated_agent_days),
    },
    {
      label: "Distributor trip cost proxy · break-even fee per trip",
      a: `${bdtCompact(v1.distributor.logistics_cost_proxy_bdt)} · ${bdt(v1.distributor.break_even_fee_per_trip_bdt)}`,
      b: `${bdtCompact(v2.distributor.logistics_cost_proxy_bdt)} · ${bdt(v2.distributor.break_even_fee_per_trip_bdt)}`,
      est: true,
    },
    {
      label: "Peer logistics cost per est. transaction protected",
      a: bdt(v1.economics.peer_cost_per_estimated_transaction_protected_bdt),
      b: bdt(v2.economics.peer_cost_per_estimated_transaction_protected_bdt),
      est: true,
    },
    {
      label: "Break-even commission rate (covers peer logistics cost)",
      a: `${num(e1.break_even_commission_bps)} bps`,
      b: `${num(e2.break_even_commission_bps)} bps`,
      est: true,
    },
  ];

  return (
    <Card className="mt-4">
      <CardHeader
        title="Business Impact — Synthetic Simulation"
        subtitle={`Same liquidity. Placed ahead of demand. The same 14 held-out days translated into customer, agent and distributor terms. ${BIZ_LABEL}`}
        right={<SourceTag kind="sim" />}
      />
      <div className="space-y-4 px-5 py-4">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch" role="list" aria-label="From technical impact to business impact">
          <Step
            eyebrow="Technical impact"
            value={`${num(v2.customer.shortage_agent_hours_avoided)} fewer`}
            sub="shortage agent-hours with policy V2 (measured in the simulation)"
          />
          <ArrowRight className="hidden h-4 w-4 shrink-0 self-center text-slate-400 lg:block" aria-hidden />
          <Step
            eyebrow="Customers"
            value={`≈ ${num(v2.customer.estimated_transactions_protected)} transactions`}
            sub={`${bdtCompact(v2.customer.cash_out_value_protected_bdt)} cash-out served that was unmet (est. range ${num(lo)}–${num(hi)} transactions)`}
            tag={<EstimateTag />}
          />
          <ArrowRight className="hidden h-4 w-4 shrink-0 self-center text-slate-400 lg:block" aria-hidden />
          <Step
            eyebrow="Agents"
            value={bdt(v2.agent.illustrative_commission_protected_bdt)}
            sub={`illustrative commission at an assumed ${bps} bps on protected value`}
            tag={<EstimateTag />}
          />
          <ArrowRight className="hidden h-4 w-4 shrink-0 self-center text-slate-400 lg:block" aria-hidden />
          <Step
            eyebrow="Distributor · logistics"
            value={`${num(p2.peer_transfers)} transfers · ${num(p2.escalated_agent_days)} trips`}
            sub={`peer cost proxy ${bdtCompact(p2.peer_logistics_cost_bdt)}; distributor proxy ${bdtCompact(p2.distributor_cost_proxy_one_trip_per_agent_day_bdt)}`}
            tag={<EstimateTag />}
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Business KPI vs status quo · 14 held-out days</th>
                <th className="py-1.5 pr-3 text-right font-medium">AgentFlow V1</th>
                <th className="py-1.5 text-right font-medium">AgentFlow V2</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className="py-1.5 pr-3 text-slate-700">
                    {r.label}
                    {r.est && <span className="ml-1.5 text-[11px] font-medium text-amber-800">· simulated estimate</span>}
                  </td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{r.a}</td>
                  <td className="num whitespace-nowrap py-1.5 text-right font-semibold text-slate-900">{r.b}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1.5 text-xs text-slate-500">
            Status quo: {bdtCompact(sq.unmet_cash_out_bdt)} unmet of {bdtCompact(sq.requested_cash_out_bdt)} requested ({pct(sq.demand_fill_rate_pct, 2)}{" "}
            filled), ≈ {num(sq.estimated_failed_transactions)} failed transactions of {num(sq.requested_cash_out_transactions)} requested. Values are measured
            in the simulation; transaction counts are estimated (unmet BDT ÷ average synthetic cash-out ticket).
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-[13px] leading-relaxed text-slate-700 lg:col-span-3">
            <b>Honest reading.</b> At an assumed {bps} bps, the agent commission on protected cash-out ({bdt(e2.illustrative_commission_protected_bdt)}) does
            not cover the peer logistics cost proxy ({bdt(e2.operational_logistics_cost_bdt)}
            ): net {signedBdt(e2.net_illustrative_value_bdt)}. Commission alone would need about {num(e2.break_even_commission_bps)} bps to break even. The case
            rests on customers served and on cheaper delivery: V2 needs {bdt(v2.economics.peer_cost_per_estimated_transaction_protected_bdt)} of logistics per
            protected transaction against {bdt(v1.economics.peer_cost_per_estimated_transaction_protected_bdt)} for V1. No ROI is claimed.
          </div>
          <div className="min-w-0 lg:col-span-2">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">V2 net illustrative value (BDT) · sensitivity</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" aria-label="Sensitivity of V2 net illustrative value in BDT">
                <thead className="text-slate-500">
                  <tr>
                    <th className="whitespace-nowrap py-1 pr-2 text-left font-medium">Cost ×</th>
                    {rates.map((r) => (
                      <th key={r} className="py-1 pl-2 text-right font-medium">
                        {r} bps
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {mults.map((m) => (
                    <tr key={m}>
                      <td className="py-1 pr-2 text-slate-600">×{m}</td>
                      {rates.map((r) => {
                        const g = cell(m, r);
                        return (
                          <td
                            key={r}
                            className={cx(
                              "num whitespace-nowrap py-1 pl-2 text-right",
                              (g?.net_illustrative_value_bdt ?? 0) < 0 ? "text-slate-700" : "text-emerald-700",
                            )}
                          >
                            {shortSigned(g?.net_illustrative_value_bdt)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Break-even commission:{" "}
              {sens.break_even_commission_bps_by_cost_multiplier.map((b) => `cost ×${b.cost_multiplier} → ${num(b.break_even_commission_bps)} bps`).join(" · ")}
            </p>
          </div>
        </div>

        <p className="flex items-start gap-1.5 text-xs font-medium text-amber-900">
          <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>
            {BIZ_LABEL} The {bps} bps commission is an illustrative assumption, not upay&apos;s or any provider&apos;s rate; costs use the Phase-2 synthetic
            operational-cost proxy. The Phase-1 results above are unchanged.
          </span>
        </p>
      </div>
    </Card>
  );
}

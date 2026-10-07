import { CheckCircle2, FlaskConical, XCircle } from "lucide-react";
import { bdt, num, pct } from "@/lib/format";
import type { MlExperiment } from "@/lib/types";
import { Card, CardHeader, SourceTag, cx } from "@/components/ui";

export const ML_EXPERIMENT_LABEL = "Synthetic controlled experiment — selection on training-period validation folds only; held-out evaluated once.";

const ORDER = ["50", "45", "40", "35", "30", "25"];

/** "+0.3%" / "−2.0%" with a true minus sign. */
function signed(x: number | undefined): string {
  if (x === undefined || Number.isNaN(x)) return "—";
  return `${x < 0 ? "−" : "+"}${num(Math.abs(x), 1)}%`;
}

const NAMES: Record<string, string> = {
  spatial: "Spatial / neighbour aggregates",
  temporal: "Temporal regime features",
  spatial_temporal: "Spatial + temporal",
  temporal_ensemble: "Temporal + 3-seed ensemble",
};

function Verdict({ ok, title, value, sub }: { ok: boolean; title: string; value: string; sub: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-3">
      <div className={cx("flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide", ok ? "text-emerald-700" : "text-rose-700")}>
        <Icon className="h-3.5 w-3.5" aria-hidden /> {title}
      </div>
      <div className="mt-1 text-lg font-semibold text-slate-900">{value}</div>
      <div className="text-xs leading-snug text-slate-600">{sub}</div>
    </div>
  );
}

/** Targeted ML experiment (Phase 2): current serving model vs the validation-selected candidates. */
export function MlExperimentCard({ ex }: { ex: MlExperiment }) {
  const cur = ex.results.current;
  const cand = ex.results.candidate;
  const df = ex.decisions.forecast;
  const da = ex.decisions.alert_operating_point;
  const t = `${da.threshold}`;
  const hi = cur.alerts.thresholds["50"];
  const op = cur.alerts.thresholds[t];
  const c = df.checks ?? {};
  const rows: { label: string; a: string; b: string; rule: string; ok?: boolean }[] = cand
    ? [
        {
          label: "Peak-requirement MAE (6h)",
          a: bdt(cur.forecast.peak_requirement_mae),
          b: bdt(cand.forecast.peak_requirement_mae),
          rule: "≥ 3% below current",
          ok: c.peak_mae_at_least_3pct_below_current,
        },
        {
          label: "Peak MAE vs seasonal baseline",
          a: `−${num(df.current_peak_mae_improvement_vs_seasonal_pct, 1)}%`,
          b: `−${num(df.peak_mae_improvement_vs_seasonal_pct, 1)}%`,
          rule: "≥ 10% better",
          ok: c.peak_mae_at_least_10pct_below_seasonal,
        },
        {
          label: "Cash-out demand MAE",
          a: bdt(cur.forecast.cash_demand_mae),
          b: bdt(cand.forecast.cash_demand_mae),
          rule: "not > 1% worse",
          ok: c.cash_demand_mae_not_worse_than_1pct,
        },
        {
          label: "P90 coverage (nominal 90%)",
          a: pct(100 * cur.forecast.p90_coverage, 1),
          b: pct(100 * cand.forecast.p90_coverage, 1),
          rule: "87–93%",
          ok: c.p90_coverage_in_range,
        },
        {
          label: "HIGH+ recall · precision",
          a: `${pct(100 * hi.recall, 1)} · ${pct(100 * hi.precision, 1)}`,
          b: `${pct(100 * cand.alerts.thresholds["50"].recall, 1)} · ${pct(100 * cand.alerts.thresholds["50"].precision, 1)}`,
          rule: "recall ≥ −1 pp, precision ≥ −5 pp",
          ok: c.high_plus_recall_not_down_more_than_1pp && c.high_plus_precision_not_down_more_than_5pp,
        },
        {
          label: "V2 shortage events (held-out)",
          a: num(cur.v2.shortage_events),
          b: num(cand.v2.shortage_events),
          rule: "not > 2% worse",
          ok: c.v2_shortage_events_not_worse_than_2pct,
        },
        {
          label: "V2 unmet cash-out",
          a: bdt(cur.v2.unmet_cash_demand_bdt),
          b: bdt(cand.v2.unmet_cash_demand_bdt),
          rule: "not > 2% worse",
          ok: c.v2_unmet_not_worse_than_2pct,
        },
        {
          label: "V2 donor shortage events",
          a: num(cur.v2.donor_shortage_events_after_transfer),
          b: num(cand.v2.donor_shortage_events_after_transfer),
          rule: "at most +2",
          ok: c.v2_donor_shortages_at_most_2_more,
        },
      ]
    : [];
  const val = ex.preregistration.validation_forecast;
  return (
    <Card className="mt-4" id="ml-experiment">
      <CardHeader
        title="Targeted ML experiment — current vs candidate"
        subtitle={`Can the peak-requirement forecast or the early-warning recall improve? Criteria were fixed before the held-out run. ${ML_EXPERIMENT_LABEL}`}
        right={<SourceTag kind="model" />}
      />
      <div className="space-y-4 px-5 py-4">
        <div className="flex flex-col gap-2 lg:flex-row">
          <Verdict
            ok={df.promoted}
            title={df.promoted ? "Forecast candidate promoted" : "Forecast candidate rejected"}
            value={df.promoted ? "Serving model replaced" : "Serving model unchanged"}
            sub={
              df.candidate
                ? `${NAMES[df.candidate] ?? df.candidate}: peak MAE ${signed(df.peak_mae_change_vs_current_pct)} vs current (needed −3%), −${num(df.peak_mae_improvement_vs_seasonal_pct, 1)}% vs seasonal (needed −10%).`
                : "No candidate passed the validation gate."
            }
          />
          <Verdict
            ok={da.promoted}
            title={da.promoted ? "Alert operating point adopted" : "Alert operating point not adopted"}
            value={`Early warning at ${da.equivalent_level}`}
            sub={`Recall ${pct(100 * op.recall, 1)} vs ${pct(100 * hi.recall, 1)} for HIGH+; precision ${pct(100 * op.precision, 1)} vs ${pct(100 * hi.precision, 1)}. Risk levels and rebalancing are unchanged.`}
          />
        </div>

        {cand && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-[13px]" aria-label="Current model versus candidate on the held-out period">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">Held-out metric · 14 days</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Current (serving)</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Candidate</th>
                  <th className="py-1.5 pr-3 font-medium">Pre-registered rule</th>
                  <th className="py-1.5 text-right font-medium">Pass</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.label}>
                    <td className="py-1.5 pr-3 text-slate-700">{r.label}</td>
                    <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{r.a}</td>
                    <td className="num whitespace-nowrap py-1.5 pr-3 text-right font-semibold text-slate-900">{r.b}</td>
                    <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-slate-500">{r.rule}</td>
                    <td className={cx("py-1.5 text-right text-xs font-semibold", r.ok ? "text-emerald-700" : "text-rose-700")}>{r.ok ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
          <div className="min-w-0 xl:col-span-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Alert operating points · current model, held-out</div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-xs" aria-label="Precision and recall by risk-score threshold">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1 pr-2 text-left font-medium">Alert when risk score ≥</th>
                    <th className="py-1 pl-2 text-right font-medium">Recall</th>
                    <th className="py-1 pl-2 text-right font-medium">Precision</th>
                    <th className="py-1 pl-2 text-right font-medium">False alert-hours / 100 agents / day</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ORDER.filter((k) => cur.alerts.thresholds[k])
                    .map((k) => [k, cur.alerts.thresholds[k]] as const)
                    .map(([k, v]) => (
                      <tr key={k} className={cx(k === t && "bg-emerald-50/60 font-semibold", k === "50" && "bg-blue-50/40")}>
                        <td className="py-1 pr-2">
                          {k}
                          {k === "50" ? " (HIGH+, rebalancing)" : k === t ? " (MEDIUM+, adopted early warning)" : ""}
                        </td>
                        <td className="num py-1 pl-2 text-right">{pct(100 * v.recall, 1)}</td>
                        <td className="num py-1 pl-2 text-right">{pct(100 * v.precision, 1)}</td>
                        <td className="num py-1 pl-2 text-right">{num(v.false_alert_hours_per_100_agents_per_day, 1)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-[13px] leading-relaxed text-slate-700 xl:col-span-2">
            <b>Honest reading.</b> No feature or ensemble candidate earned promotion, so the published forecasts and metrics are unchanged. Spatial aggregates
            made validation error worse ({signed(val.spatial?.validation_peak_mae_change_pct ?? 0)}): the synthetic generator has no cross-agent demand
            correlation. The recall gain comes from the alert operating point, not from a better model: MEDIUM+ catches more shortages at lower precision.
          </div>
        </div>
        <p className="text-xs text-slate-500">
          <FlaskConical className="mr-1 inline h-3.5 w-3.5 align-[-2px]" aria-hidden /> {ML_EXPERIMENT_LABEL} Reproduce with{" "}
          <code className="rounded bg-slate-100 px-1">{ex.command}</code> · {ex.version}
        </p>
      </div>
    </Card>
  );
}

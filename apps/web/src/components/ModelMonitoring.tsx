"use client";

import { useApi } from "@/lib/api";
import { Card, CardHeader, ErrorState, Loading, cx } from "@/components/ui";

type Quality = { rows: number; missing: number; invalid: number; out_of_range: number; valid: number };
type Status = "STABLE" | "WATCH" | "DRIFT" | "INSUFFICIENT_DATA";
type Monitoring = {
  version: string;
  label: string;
  reference: { start: string | null; end: string | null; rows: number };
  current: { start: string | null; end: string | null; rows: number };
  features: { name: string; label: string; psi: number | null; status: Status; reference_quality: Quality; current_quality: Quality }[];
  summary: { statuses: Record<Status, number>; human_review_recommended: boolean };
};

const TONES: Record<Status, string> = {
  STABLE: "bg-emerald-50 text-emerald-800",
  WATCH: "bg-amber-50 text-amber-800",
  DRIFT: "bg-red-50 text-red-800",
  INSUFFICIENT_DATA: "bg-slate-100 text-slate-700",
};
const count = (n: number) => n.toLocaleString("en-US");
const bad = (q: Quality) => q.missing + q.invalid + q.out_of_range;
const dates = (p: Monitoring["reference"]) => `${p.start?.slice(0, 10) ?? "unavailable"} to ${p.end?.slice(0, 10) ?? "unavailable"}`;

export function ModelMonitoringCard() {
  const { data, error, reload } = useApi<Monitoring>("/api/model-monitoring");
  return (
    <section id="model-monitoring" aria-label="Model Drift and Data Quality" className="mt-8 min-w-0">
      <Card>
        <CardHeader title="Model Drift & Data Quality" subtitle="Synthetic monitoring prototype - not live upay telemetry. Historical intraday inputs only; Morning Plan excluded." />
        {error ? (
          <div className="p-4">
            <p className="mb-2 text-sm text-slate-600">Monitoring evidence unavailable. No healthy status is assumed; other evaluations remain independent.</p>
            <ErrorState message={error} onRetry={reload} />
          </div>
        ) : !data ? <Loading /> : (
          <div className="space-y-4 p-4 sm:p-5">
            <p className="text-sm text-slate-600">
              Training reference: {dates(data.reference)} ({count(data.reference.rows)} rows). Held-out inputs: {dates(data.current)} ({count(data.current.rows)} rows).
              This is a fixed historical comparison, not the selected demo hour or live model health.
            </p>
            <div className="flex flex-wrap gap-2 text-xs font-semibold" aria-label="Feature drift summary">
              {(Object.keys(TONES) as Status[]).map((s) => (
                <span key={s} className={cx("rounded-md px-2.5 py-1.5", TONES[s])}>{s.replaceAll("_", " ")}: {data.summary.statuses[s]}</span>
              ))}
            </div>
            <div className="max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label="Feature drift table, scroll horizontally on small screens">
              <table className="w-full min-w-[660px] text-left text-[13px]">
                <thead className="border-b border-slate-200 text-xs text-slate-500">
                  <tr><th className="py-2 pr-4">Input feature</th><th className="px-2 py-2 text-right">PSI</th><th className="px-3 py-2">Status</th><th className="px-2 py-2 text-right">Reference bad cells</th><th className="py-2 pl-2 text-right">Held-out missing / invalid / range</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.features.map((f) => (
                    <tr key={f.name}>
                      <td className="py-2.5 pr-4 font-medium text-slate-700">{f.label}</td>
                      <td className="num px-2 py-2.5 text-right">{f.psi === null ? "N/A" : f.psi.toFixed(3)}</td>
                      <td className="px-3 py-2.5"><span className={cx("whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold", TONES[f.status])}>{f.status.replaceAll("_", " ")}</span></td>
                      <td className="num px-2 py-2.5 text-right">{count(bad(f.reference_quality))}</td>
                      <td className="num whitespace-nowrap py-2.5 pl-2 text-right">{count(f.current_quality.missing)} / {count(f.current_quality.invalid)} / {count(f.current_quality.out_of_range)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
              <b>{data.summary.human_review_recommended ? "Human review recommended." : "No review threshold crossed in these inputs."}</b>{" "}
              A changed input distribution is not proof of forecast failure or fraud. No automatic retraining, policy changes or money movement.
            </p>
            <details className="text-xs leading-relaxed text-slate-500">
              <summary className="cursor-pointer font-medium text-slate-700">Method and limits</summary>
              <p className="mt-2">PSI compares distributions using training-only quantile bins with open-ended tails and probability smoothing. Illustrative thresholds: STABLE below 0.10; WATCH from 0.10 to below 0.25; DRIFT from 0.25. Fewer than 100 valid samples in either window means insufficient data, not stability.</p>
              <p className="mt-2">Quality counts are feature cells, not unique transactions. Missing, non-numeric/non-finite, and negative values are counted separately; fractional transaction counts are invalid-range values. The first 7 days of feature warm-up and the 6-hour split gap are excluded. No future targets are used. Seasonality and agent mix may explain shifts; this does not measure live freshness or model accuracy.</p>
            </details>
          </div>
        )}
      </Card>
    </section>
  );
}

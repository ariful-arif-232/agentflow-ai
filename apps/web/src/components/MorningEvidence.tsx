"use client";

import { AlertTriangle, FlaskConical } from "lucide-react";
import type { MorningPlanEvidence } from "@/lib/types";
import { Card, CardHeader, SourceTag } from "./ui";

function Stat({ value, label, tone = "text-slate-900" }: { value: string; label: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div className={`num text-lg font-semibold leading-tight ${tone}`}>{value}</div>
      <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{label}</div>
    </div>
  );
}

/** Historical synthetic research evidence for the full-day Morning Plan (never an expected saving for a date). */
export function MorningEvidencePanel({ ev, compact = false }: { ev: MorningPlanEvidence; compact?: boolean }) {
  const c = ev.combined_unmet_reduction_pct;
  const seeds = `${ev.audit_seeds[0]}–${ev.audit_seeds[ev.audit_seeds.length - 1]}`;
  return (
    <Card>
      <CardHeader
        title="Does ML add value beyond simple cautious rules?"
        subtitle={`Historical synthetic research evidence · fresh audit worlds ${seeds} (same synthetic world family) · frozen full-day ML P90 vs the best cautious historical rule (7-day q90)`}
        right={<SourceTag kind="sim" />}
      />
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          <Stat value={`${ev.worlds_improved}/${ev.worlds_total}`} label="synthetic worlds improved" tone="text-emerald-700" />
          <Stat value={`${c.median.toFixed(1)}%`} label="median lower combined unmet" tone="text-emerald-700" />
          <Stat value={`${c.min.toFixed(1)}–${c.max.toFixed(1)}%`} label="range across worlds" />
          <Stat value={`${ev.cash_unmet_reduction_pct_median.toFixed(1)}%`} label="median lower unmet cash-out" />
          <Stat value={`${ev.efloat_unmet_reduction_pct_median.toFixed(1)}%`} label="median lower unmet cash-in (e-float)" />
          <Stat value={`BDT ${ev.extra_working_capital_bdt}`} label="extra working capital" tone="text-blue-700" />
        </div>
        <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2.5 text-xs leading-relaxed text-amber-950" role="note">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden />
          <div>
            <span className="font-semibold">Caveats. </span>
            Synthetic worlds — not upay data and not a guaranteed saving. Cash P90 coverage is{" "}
            {(100 * ev.pooled_p90_coverage.cash).toFixed(1)}% (nominal 90%), so the cautious forecast under-covers cash.
            Low-volume agents did worse than the q90 rule in 4 of 5 audit worlds, and rural e-float allocations can fall
            materially — both need human review. This is not an expected saving for the selected date.
          </div>
        </div>
        {!compact && (
          <details className="text-xs text-slate-600">
            <summary className="cursor-pointer font-medium text-slate-700">
              <FlaskConical className="mr-1 inline h-3.5 w-3.5" aria-hidden />
              How we got here (pre-registered research path, including rejected ideas)
            </summary>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {ev.research_path.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            <p className="mt-2">
              Forecast accuracy: the full-day ML P50 error is {ev.forecast_mae_improvement_vs_mean7_median_pct.cash.toFixed(1)}%
              (cash) and {ev.forecast_mae_improvement_vs_mean7_median_pct.efloat.toFixed(1)}% (e-float) lower than the 7-day
              mean (median across audit worlds). P90 coverage: cash {(100 * ev.pooled_p90_coverage.cash).toFixed(1)}%, e-float{" "}
              {(100 * ev.pooled_p90_coverage.efloat).toFixed(1)}%.
            </p>
          </details>
        )}
      </div>
    </Card>
  );
}

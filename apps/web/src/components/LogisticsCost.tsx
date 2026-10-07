import { FlaskConical } from "lucide-react";
import { num } from "@/lib/format";
import { cx } from "@/components/ui";

export const COST_PROXY_NOTE = "Simulated operational-cost proxy — replace assumptions with governed operator rates for deployment.";

/** BDT with two decimals so the shown components add up exactly to the shown total. */
export function bdt2(x: number | null | undefined): string {
  return x === null || x === undefined || Number.isNaN(x) ? "—" : `BDT ${num(x, 2)}`;
}

export interface CostParts {
  base_handling_bdt: number;
  distance_cost_bdt: number;
  time_cost_bdt: number;
  cash_in_transit_cost_bdt: number;
}

export function sumParts(items: CostParts[]): CostParts {
  const add = (k: keyof CostParts) => Math.round(items.reduce((a, c) => a + c[k], 0) * 100) / 100;
  return { base_handling_bdt: add("base_handling_bdt"), distance_cost_bdt: add("distance_cost_bdt"), time_cost_bdt: add("time_cost_bdt"), cash_in_transit_cost_bdt: add("cash_in_transit_cost_bdt") };
}

/** Label every cost figure must carry. */
export function CostProxyNote({ className }: { className?: string }) {
  return (
    <p className={cx("flex items-start gap-1.5 text-xs font-medium text-amber-900", className)}>
      <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{COST_PROXY_NOTE}</span>
    </p>
  );
}

/** handling + distance + time + cash-in-transit = total, as an equation of four terms. */
export function CostEquation({ parts, total, details }: { parts: CostParts; total: number; details?: Partial<Record<keyof CostParts, string>> }) {
  const terms: { key: keyof CostParts; label: string }[] = [
    { key: "base_handling_bdt", label: "Handling" },
    { key: "distance_cost_bdt", label: "Distance" },
    { key: "time_cost_bdt", label: "Field time" },
    { key: "cash_in_transit_cost_bdt", label: "Cash-in-transit" },
  ];
  return (
    <div className="flex flex-wrap items-stretch gap-1.5 text-xs" role="group" aria-label="Operational cost breakdown">
      {terms.map((t, i) => (
        <span key={t.key} className="flex items-center gap-1.5">
          <span className="rounded-md bg-slate-50 px-2 py-1 ring-1 ring-inset ring-slate-200">
            <span className="block text-[11px] text-slate-500">{t.label}</span>
            <span className="num block font-semibold text-slate-900">{bdt2(parts[t.key])}</span>
            {details?.[t.key] && <span className="block text-[11px] text-slate-500">{details[t.key]}</span>}
          </span>
          <span className="font-semibold text-slate-400" aria-hidden>
            {i < terms.length - 1 ? "+" : "="}
          </span>
        </span>
      ))}
      <span className="rounded-md bg-blue-50 px-2 py-1 ring-1 ring-inset ring-blue-200">
        <span className="block text-[11px] text-blue-800">Estimated logistics cost</span>
        <span className="num block font-semibold text-blue-900">{bdt2(total)}</span>
      </span>
    </div>
  );
}

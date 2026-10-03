"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, pct } from "@/lib/format";
import type { AgentDetail, ImpactResponse, Overview } from "@/lib/types";
import { cx } from "./ui";

/** The documented demo case (docs/DEMO_SCRIPT.md). Values below are read live from the API. */
export const DEMO_AGENT = "AG-0171";

interface Step {
  n: number;
  title: string;
  detail: string;
  href: string;
  match: (path: string) => boolean;
}

export function DemoGuide() {
  const { defaultAsOf, asOf, guideOpen, setGuideOpen } = useAsOf();
  const path = usePathname();
  const on = guideOpen && !!defaultAsOf;
  const ov = useApi<Overview>(on ? "/api/overview" : null, { as_of: defaultAsOf });
  const ag = useApi<AgentDetail>(on ? `/api/agents/${DEMO_AGENT}` : null, { as_of: defaultAsOf });
  const imp = useApi<ImpactResponse>(on ? "/api/impact" : null);
  if (!on) return null;

  const rec = ag.data?.recommendations.as_destination[0];
  const dflt = imp.data?.deployment_decision.default_policy;
  const vs = imp.data ? (dflt === "v2" ? imp.data.agentflow_v2_vs_status_quo : imp.data.agentflow_vs_status_quo) : null;
  const cov = ag.data?.risk.coverage_ratio;
  const steps: Step[] = [
    {
      n: 1,
      title: "Network risk",
      detail: ov.data ? `${ov.data.kpis.at_risk_agents} agents HIGH/CRITICAL in the next 6h` : "Command Center",
      href: "/",
      match: (p) => p === "/",
    },
    {
      n: 2,
      title: "Morning Plan",
      detail: "07:00 predict → 08:00 position cash + e-float · same working capital",
      href: "/morning-plan",
      match: (p) => p.startsWith("/morning-plan"),
    },
    {
      n: 3,
      title: `Explain ${DEMO_AGENT}`,
      detail: ag.data
        ? `${ag.data.risk.risk_level} risk ${ag.data.risk.risk_score.toFixed(0)}/100${cov !== null && cov !== undefined ? ` · cash covers ~${(100 * cov).toFixed(0)}% of need` : ""}`
        : "Intraday risk and evidence-based reasons",
      href: `/agents/${DEMO_AGENT}#why`,
      match: (p) => p.startsWith("/agents/"),
    },
    {
      n: 4,
      title: "V2 intraday rebalancing",
      detail: rec ? `${rec.id}: ${bdt(rec.recommended_amount)} from ${rec.source_agent}` : "Recipient benefit & donor safety",
      href: `/rebalancing?focus=${DEMO_AGENT}`,
      match: (p) => p.startsWith("/rebalancing"),
    },
    {
      n: 5,
      title: "Approve Simulation",
      detail: "Human review · simulation only — no money moves",
      href: `/rebalancing?focus=${DEMO_AGENT}`,
      match: () => false,
    },
    {
      n: 6,
      title: "Measure impact",
      detail: vs ? `Unmet demand −${pct(vs.unmet_demand_reduction_pct, 1)} vs status quo (held-out)` : "Status quo vs V1 vs V2",
      href: "/impact",
      match: (p) => p.startsWith("/impact"),
    },
  ];
  const offDefault = asOf && defaultAsOf && asOf !== defaultAsOf;

  return (
    <section aria-label="Judge demo guide" className="af-rise mb-5 rounded-xl border border-blue-200 bg-gradient-to-b from-blue-50/80 to-white px-4 py-3.5">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-blue-900">
          Judge demo · snapshot Mon 31 Aug 2026, 13:00 · live values
          {offDefault && <span className="ml-2 font-normal normal-case tracking-normal text-amber-800">(you are viewing a different decision time — use Reset demo)</span>}
        </div>
        <button onClick={() => setGuideOpen(false)} aria-label="Close judge demo guide" className="rounded p-1 text-blue-900 hover:bg-blue-100">
          <X className="h-4 w-4" />
        </button>
      </div>
      <ol className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {steps.map((s) => {
          const current = s.match(path);
          return (
            <li key={s.n}>
              <Link
                href={s.href}
                aria-current={current ? "step" : undefined}
                className={cx(
                  "af-lift block h-full rounded-lg border px-3 py-2.5 text-left",
                  current ? "border-blue-600 bg-white shadow-sm ring-1 ring-blue-600/20" : "border-blue-100 bg-white/80 hover:border-blue-300",
                )}
              >
                <div className="flex items-center gap-2 text-[13px] font-semibold text-slate-900">
                  <span className={cx("inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] text-white", current ? "bg-blue-700" : "bg-slate-800")}>{s.n}</span>
                  {s.title}
                </div>
                <div className="mt-1 text-xs leading-snug text-slate-600">{s.detail}</div>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

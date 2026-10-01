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
      title: `Open ${DEMO_AGENT}`,
      detail: ag.data ? `${ag.data.risk.risk_level} risk · ${ag.data.risk.risk_score.toFixed(0)}/100` : "Agent Intelligence",
      href: `/agents/${DEMO_AGENT}`,
      match: (p) => p.startsWith("/agents/"),
    },
    {
      n: 3,
      title: "Why this risk?",
      detail: cov !== null && cov !== undefined ? `Cash covers ~${(100 * cov).toFixed(0)}% of forecast peak need` : "Evidence-based reasons",
      href: `/agents/${DEMO_AGENT}#why`,
      match: () => false,
    },
    {
      n: 4,
      title: "V2 recommendation",
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
    <section aria-label="Judge demo guide" className="mb-5 rounded-xl border border-blue-200 bg-blue-50/50 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-blue-900">
          Judge demo · snapshot Mon 31 Aug 2026, 13:00 · live values
          {offDefault && <span className="ml-2 font-normal normal-case text-amber-800">(you are viewing a different decision time — use Reset demo)</span>}
        </div>
        <button onClick={() => setGuideOpen(false)} aria-label="Close judge demo guide" className="rounded p-1 text-blue-900 hover:bg-blue-100">
          <X className="h-4 w-4" />
        </button>
      </div>
      <ol className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {steps.map((s) => (
          <li key={s.n}>
            <Link
              href={s.href}
              className={cx(
                "block h-full rounded-lg border px-3 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600",
                s.match(path) ? "border-blue-600 bg-white shadow-sm" : "border-blue-100 bg-white/70 hover:border-blue-300",
              )}
            >
              <div className="text-xs font-semibold text-slate-900">
                <span className="mr-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-700 text-[10px] text-white">{s.n}</span>
                {s.title}
              </div>
              <div className="mt-0.5 text-[11px] leading-snug text-slate-600">{s.detail}</div>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

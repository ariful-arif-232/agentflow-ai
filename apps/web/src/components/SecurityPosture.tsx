"use client";

import { CheckCircle2, ShieldAlert, ShieldCheck, Wrench } from "lucide-react";
import { useApi } from "@/lib/api";
import { num } from "@/lib/format";
import { Card, CardHeader, cx } from "@/components/ui";

interface SecurityStatus {
  label: string;
  rate_limit: { label: string; enabled: boolean; max_requests: number; window_seconds: number; scope: string };
  audit: { verified: boolean; records: number; head_hash: string; storage: string; note: string };
  authentication: string;
}

const COLUMNS = [
  {
    title: "Implemented now",
    icon: CheckCircle2,
    tone: "text-emerald-700",
    items: [
      "Approval is enforced by the server: a simulation without reviewer_acknowledged = true is rejected, even if the dashboard is bypassed.",
      "Financial actions are simulation-only. No payment or transfer API exists, and no money moves.",
      "Manipulation guardrail: at-risk agents with ANOMALOUS activity are held for manual review and get no automatic peer liquidity.",
      "Anomaly ≠ fraud: unusual activity is a reason to look, never a label of wrongdoing.",
    ],
  },
  {
    title: "Prototype safeguards",
    icon: Wrench,
    tone: "text-amber-800",
    items: [
      "Process-local rate limiting on the two simulation endpoints (HTTP 429 + Retry-After); read-only pages are not limited. Not an enterprise WAF.",
      "Tamper-evident audit: every simulated approval is SHA-256 hash-chained and verified; edits break the chain and new approvals are refused.",
      "Replay guard: re-submitting the same approval returns the original record instead of writing a duplicate.",
      "Optional append-only JSONL audit file (AGENTFLOW_AUDIT_LOG_PATH), re-verified at start-up.",
    ],
  },
  {
    title: "Still required for production",
    icon: ShieldAlert,
    tone: "text-slate-700",
    items: [
      "Enterprise identity and access: SSO/OAuth, role-based reviewer/approver separation and verified identity on every approval (not implemented).",
      "An external, governed, durable audit store; the prototype log is process-local unless a persistent volume is mounted.",
      "Distributed rate limiting / WAF, CSP and HSTS, dependency and image scanning.",
      "Holding WATCH-level (not only ANOMALOUS) at-risk agents for review, re-evaluated on real data.",
    ],
  },
];

export function SecurityPosture() {
  const st = useApi<SecurityStatus>("/api/security/status");
  const a = st.data?.audit;
  const r = st.data?.rate_limit;
  return (
    <Card className="mt-4">
      <CardHeader
        title="Security, approval & manipulation guardrails"
        subtitle="Prototype controls, not enterprise IAM or banking-grade infrastructure. What is enforced today, what is a prototype safeguard, and what production still needs."
      />
      <div className="grid grid-cols-1 gap-4 px-5 py-4 lg:grid-cols-3">
        {COLUMNS.map((c) => (
          <section key={c.title} aria-label={c.title}>
            <h3 className={cx("mb-2 flex items-center gap-1.5 text-sm font-semibold", c.tone)}>
              <c.icon className="h-4 w-4" aria-hidden /> {c.title}
            </h3>
            <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-slate-700">
              {c.items.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <div className="border-t border-slate-100 px-5 py-3 text-[13px] text-slate-700">
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="flex items-center gap-1.5 font-medium">
            <ShieldCheck className="h-4 w-4 text-emerald-700" aria-hidden />
            Manipulation guardrail — abnormal activity is held for review, never automatically rewarded with liquidity.
          </span>
        </p>
        <p className="mt-1.5 text-xs text-slate-500" aria-live="polite">
          {a && r ? (
            <>
              Live status: audit chain {a.verified ? "verified" : "FAILED verification — new approvals refused"} · {num(a.records)} simulated{" "}
              {a.records === 1 ? "approval" : "approvals"} · storage: {a.storage} · rate limit{" "}
              {r.enabled ? `${r.max_requests} simulations per ${num(r.window_seconds)} s per client` : "disabled"}.
            </>
          ) : st.error ? (
            "Live safeguard status is unavailable right now; the controls above are enforced by the API."
          ) : (
            "Loading live safeguard status…"
          )}
        </p>
      </div>
    </Card>
  );
}

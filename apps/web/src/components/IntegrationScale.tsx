import { Cable, CheckCircle2, Gauge, XCircle } from "lucide-react";
import { num } from "@/lib/format";
import type { IntegrationScale } from "@/lib/types";
import { Card, CardHeader, SourceTag } from "@/components/ui";

export const SCALE_LABEL = "Synthetic benchmark evidence — not real upay production performance.";

const secs = (x: number) => (x < 1 ? `${num(x * 1000)} ms` : `${num(x, 1)} s`);
const mem = (mb: number) => (mb >= 1024 ? `${num(mb / 1024, 1)} GB` : `${num(mb)} MB`);

function Tile({ icon: Icon, eyebrow, value, sub }: { icon: typeof Gauge; eyebrow: string; value: string; sub: string }) {
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        <Icon className="h-3.5 w-3.5" aria-hidden /> {eyebrow}
      </div>
      <div className="num mt-1 text-lg font-semibold text-slate-900">{value}</div>
      <div className="text-xs leading-snug text-slate-600">{sub}</div>
    </div>
  );
}

/** Integration & Scale (Phase-2): feed contract, replay equivalence and decision-path benchmark. */
export function IntegrationScaleCard({ ev }: { ev: IntegrationScale }) {
  const r = ev.replay;
  const runs = ev.benchmark.scales;
  const big = runs[runs.length - 1];
  const matched = r.targets.filter((t) => t.match).length;
  const env = ev.environment;
  return (
    <Card className="mt-4" id="integration-scale">
      <CardHeader
        title="Integration & Scale — Synthetic Benchmark"
        subtitle={`How a provider could feed AgentFlow, proof that streaming the data hour by hour gives the same decisions as the batch pipeline, and how the decision path scales. ${SCALE_LABEL}`}
        right={<SourceTag kind="data" />}
      />
      <div className="space-y-4 px-5 py-4">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
          <Tile
            icon={Cable}
            eyebrow="Feed contract"
            value={ev.contract.schema_version}
            sub={`Aggregated agent-hours only, no personal data. ${ev.contract.validation_rules.length} strict validation rules; unknown or personal-data-like fields are rejected.`}
          />
          <Tile
            icon={r.all_match ? CheckCircle2 : XCircle}
            eyebrow="Replay = batch pipeline"
            value={`${matched} / ${r.targets.length} timestamps identical`}
            sub={`${num(r.events_validated)} events replayed chronologically through the contract (${num(r.hours_replayed)} hours, ${num(r.agents)} agents); risk, anomaly and review decisions match for every agent.`}
          />
          <Tile
            icon={Gauge}
            eyebrow="Decision path at scale"
            value={`${num(big.agents)} agents · ${secs(big.hourly_refresh_seconds)}`}
            sub={`median full hourly refresh on ${env.logical_cpus} vCPUs, peak memory ${mem(big.peak_rss_mb)}; single process, no added infrastructure.`}
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[13px]" aria-label="Decision-path benchmark by number of agents">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Synthetic agents</th>
                <th className="py-1.5 pr-3 text-right font-medium">Hourly refresh</th>
                <th className="py-1.5 pr-3 text-right font-medium">Features</th>
                <th className="py-1.5 pr-3 text-right font-medium">Model inference</th>
                <th className="py-1.5 pr-3 text-right font-medium">V2 plan</th>
                <th className="py-1.5 pr-3 text-right font-medium">Contract validation</th>
                <th className="py-1.5 text-right font-medium">Peak memory</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((s) => (
                <tr key={s.agents}>
                  <td className="num py-1.5 pr-3 text-slate-700">{num(s.agents)}</td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right font-semibold text-slate-900">{secs(s.hourly_refresh_seconds)}</td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{secs(s.median_seconds.feature_build_window)}</td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{secs(s.median_seconds.engine_inference_window)}</td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{secs(s.median_seconds.plan_v2_serving)}</td>
                  <td className="num whitespace-nowrap py-1.5 pr-3 text-right">{num(s.events_per_second_validation)} events/s</td>
                  <td className="num whitespace-nowrap py-1.5 text-right">{mem(s.peak_rss_mb)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1.5 text-xs text-slate-500">
            Median of {big.repeats} runs per scale; {big.window_hours}-hour rolling window per agent. Features and model inference cover the whole window; the
            refresh also includes snapshot assembly and the V1 plan. Measured on {env.cpu_model}, Python {env.python}.
          </p>
        </div>

        <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-[13px] leading-relaxed text-slate-700">
          <b>Bottleneck, reported honestly.</b> {ev.benchmark.bottlenecks[0]} {ev.benchmark.bottlenecks[1]}
        </div>
        <p className="text-xs text-slate-500">
          {SCALE_LABEL} Deterministic file replay through the contract, not a live ledger, broker or real upay integration. Reproduce with{" "}
          <code className="rounded bg-slate-100 px-1">{ev.command}</code> · {ev.version}
        </p>
      </div>
    </Card>
  );
}

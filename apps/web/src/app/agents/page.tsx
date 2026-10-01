"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useApi } from "@/lib/api";
import { useAsOf } from "@/lib/asof";
import { bdt, ratioPct, titleCase } from "@/lib/format";
import type { AgentsResponse, AnomalyStatus, RiskLevel } from "@/lib/types";
import { AnomalyBadge, Card, ErrorState, Loading, PageHeader, RiskBadge, cx } from "@/components/ui";

const LEVELS: RiskLevel[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const ANOMS: AnomalyStatus[] = ["ANOMALOUS", "WATCH", "NORMAL"];

type SortKey = "risk_score" | "cash_balance" | "pred_cash_demand_6h" | "pred_net_requirement_6h" | "expected_shortfall" | "coverage_ratio" | "anomaly_score" | "agent_id";

export default function AgentsPage() {
  const { asOf } = useAsOf();
  const [levels, setLevels] = useState<RiskLevel[]>([]);
  const [anoms, setAnoms] = useState<AnomalyStatus[]>([]);
  const [district, setDistrict] = useState("");
  const [cluster, setCluster] = useState("");
  const [segment, setSegment] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const safeSearch = search.replace(/[^A-Za-z0-9-]/g, "");

  const { data, error, loading, reload } = useApi<AgentsResponse>(asOf ? "/api/agents" : null, {
    as_of: asOf,
    risk_level: levels,
    anomaly_status: anoms,
    district,
    cluster,
    segment,
    search: safeSearch,
    sort,
    order,
  });

  const toggle = <T,>(arr: T[], v: T, set: (x: T[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const header = (key: SortKey, label: string, right = true) => (
    <th className={cx("px-3 py-2 font-medium", right && "text-right")}>
      <button
        className="inline-flex items-center gap-1 hover:text-slate-900"
        onClick={() => {
          if (sort === key) setOrder(order === "desc" ? "asc" : "desc");
          else {
            setSort(key);
            setOrder(key === "agent_id" || key === "coverage_ratio" ? "asc" : "desc");
          }
        }}
      >
        {label}
        {sort === key && (order === "desc" ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}
      </button>
    </th>
  );

  return (
    <>
      <PageHeader title="Agents" subtitle="Every synthetic agent with its current cash, ML forecast, deterministic risk score and behavioural status. Click a column to sort; click an agent for its full intelligence view." />
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="mr-1 font-medium text-slate-500">Risk</span>
            {LEVELS.map((l) => (
              <button key={l} onClick={() => toggle(levels, l, setLevels)} className={cx("rounded-md px-2 py-1 ring-1 ring-inset", levels.includes(l) ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300")}>
                {l}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="mr-1 font-medium text-slate-500">Behaviour</span>
            {ANOMS.map((a) => (
              <button key={a} onClick={() => toggle(anoms, a, setAnoms)} className={cx("rounded-md px-2 py-1 ring-1 ring-inset", anoms.includes(a) ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300")}>
                {a === "ANOMALOUS" ? "Unusual" : titleCase(a.toLowerCase())}
              </button>
            ))}
          </div>
          <select aria-label="District" className="rounded-md border border-slate-300 px-2 py-1" value={district} onChange={(e) => setDistrict(e.target.value)}>
            <option value="">All districts</option>
            {data?.filters.districts.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <select aria-label="Location cluster" className="rounded-md border border-slate-300 px-2 py-1" value={cluster} onChange={(e) => setCluster(e.target.value)}>
            <option value="">All locations</option>
            {["urban_core", "urban_periphery", "rural"].map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </select>
          <select aria-label="Volume segment" className="rounded-md border border-slate-300 px-2 py-1" value={segment} onChange={(e) => setSegment(e.target.value)}>
            <option value="">All volume segments</option>
            {["low", "medium", "high"].map((s) => (
              <option key={s} value={s}>
                {titleCase(s)} volume
              </option>
            ))}
          </select>
          <input aria-label="Search agent ID" placeholder="Search AG-0…" className="w-32 rounded-md border border-slate-300 px-2 py-1" value={search} onChange={(e) => setSearch(e.target.value)} maxLength={20} />
          <span className="ml-auto text-slate-500">{data ? `${data.count} agents` : ""}</span>
        </div>
      </Card>
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Loading />}
      {data && (
        <Card className={cx("overflow-hidden", loading && "opacity-60")}>
          <div className="overflow-x-auto">
            <table className="w-full whitespace-nowrap text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  {header("agent_id", "Agent", false)}
                  <th className="px-3 py-2 font-medium">Location</th>
                  <th className="px-3 py-2 font-medium">Segment</th>
                  {header("cash_balance", "Current cash")}
                  {header("pred_cash_demand_6h", "6h cash-out forecast")}
                  {header("pred_net_requirement_6h", "6h peak requirement")}
                  {header("expected_shortfall", "Expected gap")}
                  {header("coverage_ratio", "Coverage")}
                  {header("risk_score", "Risk")}
                  {header("anomaly_score", "Behaviour")}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.agents.map((a) => (
                  <tr key={a.agent_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2">
                      <Link href={`/agents/${a.agent_id}`} className="font-medium text-blue-700 hover:underline">
                        {a.agent_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-slate-600">
                      {a.district}
                      <span className="text-slate-400"> · {titleCase(a.location_cluster)}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{titleCase(a.agent_volume_segment)}</td>
                    <td className="num px-3 py-2 text-right">{bdt(a.cash_balance)}</td>
                    <td className="num px-3 py-2 text-right">{bdt(a.pred_cash_demand_6h)}</td>
                    <td className="num px-3 py-2 text-right">{bdt(a.pred_net_requirement_6h)}</td>
                    <td className={cx("num px-3 py-2 text-right", a.expected_shortfall > 0 ? "font-medium text-red-600" : "text-emerald-700")}>
                      {a.expected_shortfall > 0 ? `−${bdt(a.expected_shortfall)}` : `+${bdt(a.expected_surplus)}`}
                    </td>
                    <td className="num px-3 py-2 text-right">{a.coverage_ratio === null ? "—" : ratioPct(a.coverage_ratio)}</td>
                    <td className="px-3 py-2 text-right">
                      <RiskBadge level={a.risk_level} score={a.risk_score} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <AnomalyBadge status={a.anomaly_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
            Expected gap: forecast 6h peak requirement minus current cash (red = shortfall) or cash above the P90 requirement (green = surplus). Coverage “—” means no material net requirement.
          </p>
        </Card>
      )}
    </>
  );
}

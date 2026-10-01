"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { bdt, bdtCompact, hourLabel, shortHour } from "@/lib/format";
import type { HistoryPoint, RiskLevel, TrendPoint } from "@/lib/types";
import { RISK_STYLE } from "./ui";

const axis = { fontSize: 11, fill: "#64748b" };
const compactTick = (v: number) => (Math.abs(v) >= 1e5 ? `${(v / 1e5).toFixed(0)}L` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : `${v}`);

export function RiskDistributionChart({ data }: { data: { level: RiskLevel; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey="level" tick={axis} axisLine={false} tickLine={false} />
        <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip cursor={{ fill: "#f1f5f9" }} formatter={(v) => [`${v} agents`, "Agents"]} />
        <Bar dataKey="count" isAnimationActive={false} radius={[4, 4, 0, 0]} label={{ position: "top", fontSize: 11, fill: "#334155" }}>
          {data.map((d) => (
            <Cell key={d.level} fill={RISK_STYLE[d.level].fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function NetworkTrendChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 10, right: 0, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey="timestamp" tick={axis} tickFormatter={shortHour} interval={5} axisLine={false} tickLine={false} />
        <YAxis yAxisId="h" tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} width={44} />
        <YAxis yAxisId="w" orientation="right" tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} width={44} />
        <Tooltip labelFormatter={(l) => hourLabel(String(l))} formatter={(v, n) => [bdt(Number(v)), String(n)]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area yAxisId="h" type="monotone" dataKey="cash_out" name="Hourly cash-out, actual (left axis)" fill="#dbeafe" stroke="#93c5fd" isAnimationActive={false} />
        <Bar yAxisId="h" dataKey="unmet" name="Hourly unmet cash-out (left)" fill="#dc2626" barSize={4} isAnimationActive={false} />
        <Line yAxisId="w" type="monotone" dataKey="forecast_6h" name="Next-6h forecast made at that hour (right)" stroke="#1d4ed8" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line yAxisId="w" type="monotone" dataKey="actual_6h" name="Next-6h actual, once observable (right)" stroke="#0f172a" dot={false} strokeDasharray="4 3" strokeWidth={1.5} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function AgentHistoryChart({ data }: { data: HistoryPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey="timestamp" tick={axis} tickFormatter={hourLabel} interval={11} axisLine={false} tickLine={false} />
        <YAxis tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} width={44} />
        <Tooltip labelFormatter={(l) => hourLabel(String(l))} formatter={(v, n) => [bdt(Number(v)), String(n)]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="cash_out_amount" name="Cash-out demand / h" fill="#bfdbfe" isAnimationActive={false} />
        <Bar dataKey="unmet_cash_out" name="Unmet cash-out" fill="#dc2626" isAnimationActive={false} />
        <Line type="stepAfter" dataKey="cash_balance" name="Cash balance" stroke="#0f766e" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line type="monotone" dataKey="pred_net_requirement_6h" name="Forecast 6h peak requirement" stroke="#1d4ed8" dot={false} strokeWidth={1.5} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function CompareBars({
  data,
  bars,
  height = 240,
  money = true,
  layout = "horizontal",
}: {
  data: Record<string, string | number>[];
  bars: { key: string; name: string; color: string }[];
  height?: number;
  money?: boolean;
  layout?: "horizontal" | "vertical";
}) {
  const fmt = (v: number) => (money ? bdtCompact(v) : v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={layout} margin={{ top: 10, right: 16, bottom: 0, left: layout === "vertical" ? 40 : 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={layout === "vertical"} horizontal={layout === "horizontal"} stroke="#e2e8f0" />
        {layout === "horizontal" ? (
          <>
            <XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false} />
            <YAxis tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} width={48} />
          </>
        ) : (
          <>
            <XAxis type="number" tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" tick={axis} axisLine={false} tickLine={false} width={150} />
          </>
        )}
        <Tooltip cursor={{ fill: "#f1f5f9" }} formatter={(v, n) => [fmt(Number(v)), String(n)]} />
        {bars.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {bars.map((b) => (
          <Bar key={b.key} isAnimationActive={false} dataKey={b.key} name={b.name} fill={b.color} radius={layout === "horizontal" ? [3, 3, 0, 0] : [0, 3, 3, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DailyImpactChart({ data }: { data: Record<string, number | string>[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={axis} tickFormatter={(d: string) => d.slice(5)} axisLine={false} tickLine={false} />
        <YAxis tick={axis} tickFormatter={compactTick} axisLine={false} tickLine={false} width={48} />
        <Tooltip formatter={(v, n) => [bdt(Number(v)), String(n)]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="status_quo_unmet_bdt" name="Without AgentFlow" fill="#cbd5e1" isAnimationActive={false} />
        <Bar dataKey="naive_rebalancing_unmet_bdt" name="Rebalancing w/ naive forecast" fill="#93c5fd" isAnimationActive={false} />
        <Bar dataKey="agentflow_unmet_bdt" name="With AgentFlow (ML)" fill="#1d4ed8" isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

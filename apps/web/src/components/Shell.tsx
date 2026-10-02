"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, ArrowLeftRight, FlaskConical, Gauge, LayoutDashboard, PlayCircle, RotateCcw, ShieldCheck, Sunrise, Users } from "lucide-react";
import { useAsOf } from "@/lib/asof";
import { DemoGuide } from "./DemoGuide";
import { ErrorState, Loading, cx } from "./ui";

const NAV = [
  { href: "/", label: "Command Center", icon: LayoutDashboard },
  { href: "/morning-plan", label: "Morning Plan", icon: Sunrise },
  { href: "/agents", label: "Agents", icon: Users },
  { href: "/rebalancing", label: "Rebalancing", icon: ArrowLeftRight },
  { href: "/scenario", label: "Scenario Lab", icon: FlaskConical },
  { href: "/impact", label: "Impact & Model Health", icon: Gauge },
  { href: "/responsible-ai", label: "Responsible AI", icon: ShieldCheck },
];

function AsOfPicker() {
  const { asOf, available, setAsOf, defaultAsOf } = useAsOf();
  if (!asOf || !available.length) return <span className="text-xs text-slate-400">Connecting to API…</span>;
  const days = Array.from(new Set(available.map((a) => a.slice(0, 10))));
  const day = asOf.slice(0, 10);
  const hours = available.filter((a) => a.startsWith(day));
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-medium text-slate-500">Decision time</span>
      <select
        aria-label="Decision date"
        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-800"
        value={day}
        onChange={(e) => {
          const options = available.filter((a) => a.startsWith(e.target.value));
          const sameHour = options.find((a) => a.slice(11) === asOf.slice(11));
          setAsOf(sameHour || options[0]);
        }}
      >
        {days.map((d) => (
          <option key={d} value={d}>
            {new Date(d + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" })}
          </option>
        ))}
      </select>
      <select
        aria-label="Decision hour"
        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-800"
        value={asOf}
        onChange={(e) => setAsOf(e.target.value)}
      >
        {hours.map((h) => (
          <option key={h} value={h}>
            {h.slice(11, 16)}
          </option>
        ))}
      </select>
      {defaultAsOf && asOf !== defaultAsOf && (
        <button className="text-blue-700 hover:underline" onClick={() => setAsOf(defaultAsOf)}>
          Reset
        </button>
      )}
    </div>
  );
}

function DemoControls() {
  const { guideOpen, setGuideOpen, resetDemo, status } = useAsOf();
  const router = useRouter();
  if (status !== "ready") return null;
  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => setGuideOpen(!guideOpen)}
        aria-pressed={guideOpen}
        className={cx(
          "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ring-1 ring-inset focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600",
          guideOpen ? "bg-blue-700 text-white ring-blue-700" : "bg-white text-blue-800 ring-blue-200 hover:bg-blue-50",
        )}
      >
        <PlayCircle className="h-3.5 w-3.5" /> Judge demo
      </button>
      <button
        onClick={() => {
          resetDemo();
          router.push("/");
        }}
        title="Reset demo: default decision time (Mon 31 Aug 13:00), policy V2, open the guide. Does not change any data."
        aria-label="Reset demo to the default snapshot"
        className="inline-flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
      >
        <RotateCcw className="h-3.5 w-3.5" /> Reset demo
      </button>
    </div>
  );
}

function ServiceGate({ children }: { children: React.ReactNode }) {
  const { status, error, retry } = useAsOf();
  if (status === "error") return <ErrorState message={error || "The live decision service could not be reached."} onRetry={retry} />;
  if (status === "loading") return <Loading label="Connecting to the live decision service…" />;
  return <>{children}</>;
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col bg-[#0b1220] text-slate-300 lg:flex">
        <div className="px-5 pb-5 pt-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
              <Activity className="h-4.5 w-4.5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">AgentFlow AI</div>
              <div className="text-[11px] text-slate-400">Predict. Explain. Rebalance.</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cx(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm",
                  active ? "bg-white/10 font-medium text-white" : "hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="m-3 rounded-lg border border-white/10 p-3 text-[11px] leading-relaxed text-slate-400">
          <div className="mb-1 font-semibold text-slate-200">Decision support only</div>
          Synthetic data for hackathon prototyping — not production upay data. Approvals run simulations; no money is moved.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
          <div className="flex items-center gap-2 lg:hidden">
            <span className="text-sm font-semibold">AgentFlow AI</span>
          </div>
          <nav className="flex flex-wrap gap-3 text-xs lg:hidden">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="text-slate-600 hover:text-slate-900">
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="hidden items-center gap-1.5 xl:flex" aria-label="Operating mode">
            {["Synthetic data", "Human-reviewed", "Simulation only — no money moves"].map((t) => (
              <span key={t} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600">
                {t}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <AsOfPicker />
            <DemoControls />
          </div>
        </header>
        <main className="mx-auto w-full min-w-0 max-w-[1400px] flex-1 px-4 py-6 sm:px-6">
          <ServiceGate>
            <DemoGuide />
            {children}
          </ServiceGate>
        </main>
      </div>
    </div>
  );
}

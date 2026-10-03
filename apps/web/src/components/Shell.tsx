"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeftRight, FlaskConical, Gauge, LayoutDashboard, PlayCircle, RotateCcw, ShieldCheck, Sunrise, Users } from "lucide-react";
import { useAsOf } from "@/lib/asof";
import { DemoGuide } from "./DemoGuide";
import { ErrorState, Loading, TRUST_SIGNALS, TrustChips, cx } from "./ui";

/** Full-product line. The intraday loop keeps its own line, used only where it describes the intraday system. */
export const PRODUCT_TAGLINE = "Same liquidity. Placed ahead of demand.";

const NAV_GROUPS = [
  {
    label: "Operate",
    items: [
      { href: "/", label: "Command Center", icon: LayoutDashboard },
      { href: "/morning-plan", label: "Morning Plan", icon: Sunrise },
      { href: "/agents", label: "Agents", icon: Users },
      { href: "/rebalancing", label: "Rebalancing", icon: ArrowLeftRight },
    ],
  },
  {
    label: "Evaluate",
    items: [
      { href: "/scenario", label: "Scenario Lab", icon: FlaskConical },
      { href: "/impact", label: "Impact & Model Health", icon: Gauge },
      { href: "/responsible-ai", label: "Responsible AI", icon: ShieldCheck },
    ],
  },
];
const NAV = NAV_GROUPS.flatMap((g) => g.items);

/** Brand mark: two liquidity columns (cash, e-float) with a forward marker — placed ahead of demand. */
export function BrandMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 36" className={className} aria-hidden>
      <rect width="36" height="36" rx="9" fill="#1769e8" />
      <rect x="8.5" y="15" width="5.5" height="13" rx="1.6" fill="#c7d2fe" />
      <rect x="16" y="10" width="5.5" height="18" rx="1.6" fill="#a5f3fc" />
      <path d="M24.5 13.5h4.2m0 0-2-2m2 2-2 2" stroke="#f6c51b" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <rect x="24.5" y="19" width="4.2" height="9" rx="1.4" fill="#f6c51b" />
    </svg>
  );
}

function isActive(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href);
}

function AsOfPicker() {
  const { asOf, available, setAsOf, defaultAsOf } = useAsOf();
  if (!asOf || !available.length) return <span className="text-xs text-slate-400">Connecting to API…</span>;
  const days = Array.from(new Set(available.map((a) => a.slice(0, 10))));
  const day = asOf.slice(0, 10);
  const hours = available.filter((a) => a.startsWith(day));
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-semibold uppercase tracking-wide text-slate-500">Decision time</span>
      <select
        aria-label="Decision date"
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800"
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
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800"
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
        <button className="font-medium text-blue-700 hover:underline" onClick={() => setAsOf(defaultAsOf)}>
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
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ring-1 ring-inset transition-colors",
          guideOpen ? "bg-sun-400 text-navy-900 ring-sun-500" : "bg-sun-100 text-navy-900 ring-sun-400/70 hover:bg-sun-200",
        )}
      >
        <PlayCircle className="h-4 w-4" aria-hidden /> Judge demo
      </button>
      <button
        onClick={() => {
          resetDemo();
          router.push("/");
        }}
        title="Reset demo: default decision time (Mon 31 Aug 13:00), policy V2, open the guide. Does not change any data."
        aria-label="Reset demo to the default snapshot"
        className="inline-flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300 transition-colors hover:bg-slate-50"
      >
        <RotateCcw className="h-4 w-4" aria-hidden /> Reset demo
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
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[240px] flex-col border-r border-slate-200/80 bg-white lg:flex" aria-label="AgentFlow navigation">
        <div className="px-5 pb-6 pt-6">
          <Link href="/" className="flex items-center gap-3 rounded-lg">
            <BrandMark />
            <div className="min-w-0">
              <div className="text-[15px] font-semibold tracking-tight text-navy-900">AgentFlow AI</div>
              <div className="text-[11.5px] leading-snug text-slate-500">{PRODUCT_TAGLINE}</div>
            </div>
          </Link>
        </div>
        <nav className="flex-1 space-y-5 px-3">
          {NAV_GROUPS.map((g) => (
            <div key={g.label}>
              <div className="mb-1.5 px-3 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-slate-500">{g.label}</div>
              <div className="space-y-0.5">
                {g.items.map(({ href, label, icon: Icon }) => {
                  const active = isActive(path, href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cx(
                        "group relative flex items-center gap-2.5 rounded-md px-3 py-2 text-[14px] transition-colors",
                        active ? "bg-blue-50 font-semibold text-navy-900" : "text-slate-700 hover:bg-slate-50 hover:text-navy-900",
                      )}
                    >
                      {active && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r bg-sun-400" aria-hidden />}
                      <Icon className={cx("h-[18px] w-[18px]", active ? "text-blue-600" : "text-slate-500 group-hover:text-slate-700")} aria-hidden />
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="m-3 rounded-lg border border-blue-100 bg-blue-50/60 p-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-600">Decision support only</div>
          <ul className="space-y-1.5">
            {TRUST_SIGNALS.map(({ key, label, icon: Icon }) => (
              <li key={key} className="flex items-center gap-2 text-[12.5px] text-slate-700">
                <Icon className="h-3.5 w-3.5 text-blue-600" aria-hidden />
                {label}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-600">Not production upay data. Approvals run simulations only.</p>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col lg:pl-[240px]">
        <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/95 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
            <Link href="/" className="flex items-center gap-2 lg:hidden">
              <BrandMark className="h-7 w-7" />
              <span className="text-sm font-semibold">AgentFlow AI</span>
            </Link>
            <div className="hidden items-center gap-3 lg:flex">
              <TrustChips />
              <span className="sr-only">Simulation only — no money moves</span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <AsOfPicker />
              <DemoControls />
            </div>
          </div>
          <nav aria-label="Pages" className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 py-1.5 lg:hidden">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={isActive(path, n.href) ? "page" : undefined}
                className={cx(
                  "whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium",
                  isActive(path, n.href) ? "bg-navy-900 text-white" : "text-slate-600 hover:bg-slate-100",
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto w-full min-w-0 max-w-[1440px] flex-1 px-4 py-6 sm:px-6">
          <ServiceGate>
            <DemoGuide />
            {children}
          </ServiceGate>
        </main>
      </div>
    </div>
  );
}

const grouped = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** BDT with South-Asian digit grouping, e.g. BDT 58,200 or BDT 37,09,340 */
export function bdt(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `BDT ${grouped.format(Math.round(x))}`;
}

/** Compact BDT using lakh / crore, e.g. BDT 37.1 lakh */
export function bdtCompact(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e7) return `BDT ${(x / 1e7).toFixed(2)} cr`;
  if (a >= 1e5) return `BDT ${(x / 1e5).toFixed(1)} lakh`;
  return bdt(x);
}

export function num(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(x);
}

export function pct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${x.toFixed(digits)}%`;
}

export function ratioPct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "≥ 100% (no material need)";
  return `${(100 * x).toFixed(digits)}%`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

export function hourLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", hour12: false }) + "h";
}

export function shortHour(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:00`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

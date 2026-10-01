"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useApi } from "./api";

/** Client-side keys only. The demo reset never touches backend data or model outputs. */
const AS_OF_KEY = "agentflow.asOf";
const GUIDE_KEY = "agentflow.demoGuide";

export type ServiceStatus = "loading" | "ready" | "error";

interface AsOfState {
  asOf: string | null;
  defaultAsOf: string | null;
  available: string[];
  setAsOf: (v: string) => void;
  /** Status of the live decision service (from /api/meta/time). */
  status: ServiceStatus;
  error: string | null;
  retry: () => void;
  /** Judge-demo guide visibility (client-side only). */
  guideOpen: boolean;
  setGuideOpen: (open: boolean) => void;
  /** Restore client-side demo state: default decision time, default policy, guide open. */
  resetDemo: () => void;
  /** Bumped on every demo reset so pages can clear transient UI state (drawers, toggles). */
  demoEpoch: number;
}

const Ctx = createContext<AsOfState | null>(null);

function readStorage(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    /* storage unavailable: keep state in memory only */
  }
}

export function AsOfProvider({ children }: { children: React.ReactNode }) {
  const { data, error, loading, reload } = useApi<{ default_as_of: string; available: string[] }>("/api/meta/time");
  const [asOf, setAsOfState] = useState<string | null>(null);
  const [guideOpen, setGuideOpenState] = useState(false);
  const [demoEpoch, setDemoEpoch] = useState(0);

  useEffect(() => {
    setGuideOpenState(readStorage(GUIDE_KEY) === "1");
  }, []);

  useEffect(() => {
    if (!data) return;
    const stored = readStorage(AS_OF_KEY);
    setAsOfState(stored && data.available.includes(stored) ? stored : data.default_as_of);
  }, [data]);

  const setAsOf = useCallback((v: string) => {
    setAsOfState(v);
    writeStorage(AS_OF_KEY, v);
  }, []);

  const setGuideOpen = useCallback((open: boolean) => {
    setGuideOpenState(open);
    writeStorage(GUIDE_KEY, open ? "1" : null);
  }, []);

  const resetDemo = useCallback(() => {
    writeStorage(AS_OF_KEY, null);
    if (data) setAsOfState(data.default_as_of);
    setGuideOpen(true);
    setDemoEpoch((e) => e + 1);
  }, [data, setGuideOpen]);

  const status: ServiceStatus = error ? "error" : data && asOf ? "ready" : loading || !data ? "loading" : "ready";

  const value = useMemo<AsOfState>(
    () => ({
      asOf,
      defaultAsOf: data?.default_as_of ?? null,
      available: data?.available ?? [],
      setAsOf,
      status,
      error,
      retry: reload,
      guideOpen,
      setGuideOpen,
      resetDemo,
      demoEpoch,
    }),
    [asOf, data, setAsOf, status, error, reload, guideOpen, setGuideOpen, resetDemo, demoEpoch],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAsOf(): AsOfState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAsOf must be used inside AsOfProvider");
  return v;
}

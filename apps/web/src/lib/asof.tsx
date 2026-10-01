"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useApi } from "./api";

interface AsOfState {
  asOf: string | null;
  defaultAsOf: string | null;
  available: string[];
  setAsOf: (v: string) => void;
}

const Ctx = createContext<AsOfState>({ asOf: null, defaultAsOf: null, available: [], setAsOf: () => {} });

export function AsOfProvider({ children }: { children: React.ReactNode }) {
  const { data } = useApi<{ default_as_of: string; available: string[] }>("/api/meta/time");
  const [asOf, setAsOfState] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    let stored: string | null = null;
    try {
      stored = window.sessionStorage.getItem("agentflow.asOf");
    } catch {
      stored = null;
    }
    setAsOfState(stored && data.available.includes(stored) ? stored : data.default_as_of);
  }, [data]);

  const value = useMemo<AsOfState>(
    () => ({
      asOf,
      defaultAsOf: data?.default_as_of ?? null,
      available: data?.available ?? [],
      setAsOf: (v: string) => {
        setAsOfState(v);
        try {
          window.sessionStorage.setItem("agentflow.asOf", v);
        } catch {
          /* storage unavailable: keep in memory only */
        }
      },
    }),
    [asOf, data],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAsOf() {
  return useContext(Ctx);
}

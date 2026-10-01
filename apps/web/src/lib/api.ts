"use client";

import { useCallback, useEffect, useState } from "react";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Requests that take longer than this are treated as "service unavailable" (no endless spinners). */
export const REQUEST_TIMEOUT_MS = 20_000;
export const SERVICE_UNAVAILABLE = "The live decision service could not be reached.";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Params = Record<string, string | number | string[] | undefined | null>;

function buildUrl(path: string, params?: Params): string {
  const url = new URL(API_URL + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x));
      else url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch {
    // network failure, DNS, CORS, timeout: never surface a raw browser error to the user
    throw new ApiError(0, SERVICE_UNAVAILABLE);
  } finally {
    clearTimeout(timer);
  }
}

async function parse<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = res.status >= 500 ? SERVICE_UNAVAILABLE : body?.error?.message || `Request failed (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return body as T;
}

export async function apiGet<T>(path: string, params?: Params): Promise<T> {
  const res = await fetchWithTimeout(buildUrl(path, params), { cache: "no-store" });
  return parse<T>(res);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithTimeout(buildUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse<T>(res);
}

export function useApi<T>(path: string | null, params?: Params) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const key = path ? buildUrl(path, params) : null;

  const load = useCallback(async () => {
    if (!key) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithTimeout(key, { cache: "no-store" });
      setData(await parse<T>(res));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load };
}

"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

const memory = new Map<string, string>();
const eventName = "rmf-comparison-changed";
const emptySnapshot = () => "[]";
function subscribe(listener: () => void) {
  window.addEventListener(eventName, listener);
  window.addEventListener("storage", listener);
  return () => { window.removeEventListener(eventName, listener); window.removeEventListener("storage", listener); };
}
function read(key: string): string {
  try { return sessionStorage.getItem(key) ?? "[]"; } catch { return memory.get(key) ?? "[]"; }
}
function parse(value: string): string[] {
  try {
    const ids: unknown = JSON.parse(value);
    return Array.isArray(ids) ? [...new Set(ids.filter((id): id is string => typeof id === "string" && /^\d+$/.test(id)))].slice(0, 3) : [];
  } catch { return []; }
}
export function useComparisonSelection(account?: string) {
  const key = `rmf-comparison:${account}`;
  const snapshot = useSyncExternalStore(subscribe, useCallback(() => read(key), [key]), emptySnapshot);
  const selected = useMemo(() => parse(snapshot), [snapshot]);
  const setSelected = useCallback((next: string[] | ((current: string[]) => string[])) => {
    const ids = typeof next === "function" ? next(parse(read(key))) : next;
    const value = JSON.stringify([...new Set(ids)].slice(0, 3));
    memory.set(key, value);
    try { sessionStorage.setItem(key, value); } catch { /* In-memory comparison still works. */ }
    window.dispatchEvent(new Event(eventName));
  }, [key]);
  return { selected, setSelected };
}
export function clearComparisonSelection() {
  memory.clear();
  try { for (const key of Object.keys(sessionStorage)) if (key.startsWith("rmf-comparison:")) sessionStorage.removeItem(key); } catch { /* Optional storage. */ }
  window.dispatchEvent(new Event(eventName));
}

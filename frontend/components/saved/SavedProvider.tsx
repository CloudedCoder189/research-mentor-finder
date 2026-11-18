"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  getSavedResearchers,
  saveResearcher,
  toNumericId,
  unsaveResearcher,
} from "@/lib/api/outreach";
import { toSavedResult } from "@/lib/api/map";
import { useAuth } from "@/lib/auth-context";
import type { SavedResult } from "@/types";

type SavedStatus = "loading" | "ready" | "error";

interface SavedContextValue {
  rows: SavedResult[];
  status: SavedStatus;
  error: string | null;
  isSaved: (professorId: string | number) => boolean;
  toggleSaved: (professorId: string | number) => Promise<boolean>;
  remove: (professorId: string | number) => Promise<boolean>;
  refresh: () => Promise<void>;
}

const SavedContext = createContext<SavedContextValue | null>(null);

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Could not update Saved.";
}

export function SavedProvider({ children }: { children: React.ReactNode }) {
  const { user, status: authStatus } = useAuth();
  const [rows, setRows] = useState<SavedResult[]>([]);
  const [status, setStatus] = useState<SavedStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const account = user?.user_id;
  const activeAccount = useRef(account);
  useLayoutEffect(() => { activeAccount.current = account; }, [account]);
  const loadSequence = useRef(0);
  const [rowsAccount, setRowsAccount] = useState<string | undefined>(undefined);

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    if (authStatus !== "ready") return;
    if (!user) {
      setRows([]);
      setRowsAccount(undefined);
      setError(null);
      setStatus("ready");
      return;
    }
    setStatus("loading");
    try {
      const data = await getSavedResearchers();
      if (sequence !== loadSequence.current || account !== activeAccount.current) return;
      setRows(data.results.map(toSavedResult));
      setRowsAccount(account);
      setError(null);
      setStatus("ready");
    } catch (cause) {
      if (sequence !== loadSequence.current || account !== activeAccount.current) return;
      setRows([]);
      setError(messageOf(cause));
      setStatus("error");
    }
  }, [authStatus, user, account]);

  useEffect(() => {
    void load();
    return () => { loadSequence.current += 1; };
  }, [load]);

  const isSaved = useCallback(
    (professorId: string | number) => {
      const id = String(professorId);
      return rowsAccount === account && rows.some((row) => row.researcher.id === id);
    },
    [rows, rowsAccount, account],
  );

  const remove = useCallback(
    async (professorId: string | number) => {
      const numeric = toNumericId(professorId);
      if (numeric === 0) return false;
      const id = String(professorId);
      const removed = rows.find((row) => row.researcher.id === id);
      setRows((current) => current.filter((row) => row.researcher.id !== id));
      try {
        await unsaveResearcher(numeric);
        if (account !== activeAccount.current) return false;
        setError(null);
        return true;
      } catch (cause) {
        if (account !== activeAccount.current) return false;
        setError(messageOf(cause));
        if (removed) {
          setRows((current) => [...current, removed]);
        }
        setStatus("error");
        return false;
      }
    },
    [rows, account],
  );

  const toggleSaved = useCallback(
    async (professorId: string | number): Promise<boolean> => {
      const numeric = toNumericId(professorId);
      if (numeric === 0) {
        setError("This researcher is not available to save from the directory.");
        setStatus("error");
        return false;
      }
      const currentlySaved = isSaved(professorId);
      if (currentlySaved) {
        return remove(professorId);
      }
      try {
        await saveResearcher(numeric);
        if (account !== activeAccount.current) return false;
        await load();
        return true;
      } catch (cause) {
        if (account !== activeAccount.current) return false;
        setError(messageOf(cause));
        setStatus("error");
        return false;
      }
    },
    [isSaved, load, remove, account],
  );

  const value = useMemo(
    () => ({ rows: rowsAccount === account ? rows : [], status: user && rowsAccount !== account && status !== "error" ? "loading" as const : status, error, isSaved, toggleSaved, remove, refresh: load }),
    [rows, rowsAccount, account, user, status, error, isSaved, toggleSaved, remove, load],
  );

  return <SavedContext.Provider value={value}>{children}</SavedContext.Provider>;
}

export function useSaved(): SavedContextValue {
  const value = useContext(SavedContext);
  if (!value) {
    throw new Error("useSaved must be used within <SavedProvider>.");
  }
  return value;
}

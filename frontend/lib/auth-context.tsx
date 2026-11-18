"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  beginGoogleSignIn,
  devLogin as devLoginRequest,
  getAuthStatus,
  logout as logoutRequest,
} from "@/lib/api/auth";
import { ApiError, setApiCsrfToken } from "@/lib/api/client";
import { announceAuthChange, AUTH_CHANGE_KEY, AUTH_CHECK_EVENT } from "@/lib/auth-sync";
import { clearDraftRecovery } from "@/lib/draftRecovery";
import type { AuthUserDto } from "@/lib/api/types";

type AuthStatus = "loading" | "ready";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUserDto | null;
  devLoginAvailable: boolean;
  localImportAvailable: boolean;
  signOutError: string | null;
  signingOut: boolean;
  refresh: () => Promise<void>;
  signIn: () => void;
  devSignIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUserDto | null>(null);
  const [devLoginAvailable, setDevLoginAvailable] = useState(false);
  const [localImportAvailable, setLocalImportAvailable] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const requestSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const changingSession = useRef(false);
  const lastIdentity = useRef<string | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    if (changingSession.current) return;
    const sequence = ++requestSequence.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const data = await getAuthStatus(controller.signal);
      if (sequence !== requestSequence.current) return;
      const identity = data.user?.user_id ?? null;
      const previous = lastIdentity.current;
      if (!data.user || (previous !== undefined && previous !== identity)) clearDraftRecovery();
      lastIdentity.current = identity;
      setUser(current => current && data.user &&
        current.user_id === data.user.user_id && current.email === data.user.email &&
        current.display_name === data.user.display_name && current.avatar_url === data.user.avatar_url
        ? current : data.user);
      setDevLoginAvailable(data.dev_login_available);
      setLocalImportAvailable(data.local_import_available === true);
      setApiCsrfToken(data.csrf_token);
      if (previous !== identity) announceAuthChange();
    } catch {
      if (sequence !== requestSequence.current) return;
      setUser(null);
      setDevLoginAvailable(false);
      setLocalImportAvailable(false);
      setApiCsrfToken(null);
    } finally {
      if (sequence === requestSequence.current) setStatus("ready");
    }
  }, []);

  useEffect(() => {
    const check = () => { void refresh(); };
    const visible = () => { if (document.visibilityState === "visible") check(); };
    const storage = (event: StorageEvent) => { if (event.key === AUTH_CHANGE_KEY || event.key === null) check(); };
    window.addEventListener("focus", check);
    window.addEventListener(AUTH_CHECK_EVENT, check);
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("storage", storage);
    check();
    return () => {
      requestSequence.current += 1;
      activeRequest.current?.abort();
      window.removeEventListener("focus", check);
      window.removeEventListener(AUTH_CHECK_EVENT, check);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("storage", storage);
    };
  }, [refresh]);

  const signIn = useCallback(() => {
    beginGoogleSignIn();
  }, []);

  const devSignIn = useCallback(async () => {
    changingSession.current = true;
    requestSequence.current += 1;
    activeRequest.current?.abort();
    try {
      const data = await devLoginRequest();
      lastIdentity.current = data.user?.user_id ?? null;
      setUser(data.user);
      setDevLoginAvailable(data.dev_login_available);
      setLocalImportAvailable(data.local_import_available === true);
      setApiCsrfToken(data.csrf_token);
      announceAuthChange();
    } finally {
      changingSession.current = false;
      setStatus("ready");
    }
  }, []);

  const signOut = useCallback(async () => {
    changingSession.current = true;
    requestSequence.current += 1;
    activeRequest.current?.abort();
    setSigningOut(true);
    setSignOutError(null);
    try {
      await logoutRequest();
      lastIdentity.current = null;
      clearDraftRecovery();
      setUser(null);
      setLocalImportAvailable(false);
      setApiCsrfToken(null);
      announceAuthChange();
    } catch (cause) {
      setSignOutError("Could not sign out. Check your connection and try again.");
      changingSession.current = false;
      if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) void refresh();
    } finally {
      changingSession.current = false;
      setSigningOut(false);
    }
  }, [refresh]);

  const value = useMemo(
    () => ({ status, user, devLoginAvailable, localImportAvailable, signOutError, signingOut, refresh, signIn, devSignIn, signOut }),
    [status, user, devLoginAvailable, localImportAvailable, signOutError, signingOut, refresh, signIn, devSignIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within <AuthProvider>.");
  }
  return value;
}

"use client";

import { AlertTriangle, LogIn, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";

/**
 * Explains why the Google round-trip failed. The backend redirects here with
 * ``auth=error&reason=<reason>`` (see ``api/auth/config.login_failure_url``).
 * Silently re-rendering the normal sign-in gate is what made this failure look
 * like a loop, so every reason gets an explicit explanation.
 */
const AUTH_ERROR_MESSAGES: Record<string, string> = {
  config:
    "Google sign-in is temporarily unavailable on this site. Please try again later or contact support.",
  unavailable: "Sign-in is busy right now. Please try again shortly.",
  denied: "Google sign-in was cancelled before it finished. You can try again.",
  state: "That sign-in attempt expired before it completed. Please try again.",
  verification: "Google could not verify your identity for that sign-in attempt. Please try again.",
  unknown: "Sign-in did not complete. You can try again.",
};

function useAuthError(): string | null {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("auth") !== "error") return;
      const reason = params.get("reason") ?? "unknown";
      setMessage(AUTH_ERROR_MESSAGES[reason] ?? AUTH_ERROR_MESSAGES.unknown);
    } catch {
      /* history unavailable */
    }
  }, []);

  return message;
}

export function SignInPrompt({
  title = "Sign in to continue",
  message = "Your saved researchers, research profile, and reviewed outreach drafts are stored with your account. Sign in to pick up where you left off.",
}: {
  title?: string;
  message?: string;
}) {
  const { signIn, devSignIn, devLoginAvailable } = useAuth();
  const authError = useAuthError();

  return (
    <Container className="py-10 sm:py-12">
      <section className="card mx-auto mt-10 max-w-xl p-8 text-center sm:mt-14" role="status">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-control bg-brand-50 text-brand-700">
          <UserRound className="h-6 w-6" aria-hidden="true" />
        </span>
        <h1 className="mt-4 text-xl font-bold tracking-tight text-ink">{title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">{message}</p>
        {authError ? (
          <div
            className="mt-5 flex items-start gap-2.5 rounded-control border border-amber-200 bg-amber-50 p-3 text-left"
            role="alert"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
            <p className="text-sm text-amber-900">{authError}</p>
          </div>
        ) : null}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button onClick={signIn}>
            <LogIn className="h-4 w-4" aria-hidden="true" />
            Sign in with Google
          </Button>
          {devLoginAvailable ? (
            <Button
              variant="secondary"
              onClick={() => void devSignIn()}
              aria-label="Use the local developer account"
            >
              Local developer account
            </Button>
          ) : null}
        </div>
      </section>
    </Container>
  );
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();

  if (status === "loading") {
    return (
      <Container className="py-10 sm:py-12">
        <div
          className="card mx-auto max-w-xl animate-pulse p-8 text-center sm:mt-14"
          aria-busy="true"
          aria-label="Checking your session"
        >
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-control bg-slate-200" />
          <h1 className="mt-4 text-lg font-semibold text-ink">Checking your session…</h1>
        </div>
      </Container>
    );
  }

  if (!user) {
    return (
      <Container className="py-10 sm:py-12">
        <SignInPrompt />
      </Container>
    );
  }

  return <>{children}</>;
}
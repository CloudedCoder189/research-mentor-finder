import { apiFetch, apiUrl } from "@/lib/api/client";
import type { AuthStatusDto, ImportLocalDto } from "@/lib/api/types";

export function getAuthStatus(signal?: AbortSignal): Promise<AuthStatusDto> {
  return apiFetch<AuthStatusDto>("/api/auth/me", { signal });
}

export function devLogin(): Promise<AuthStatusDto> {
  return apiFetch<AuthStatusDto>("/api/auth/dev-login", { method: "POST" });
}

export function logout(): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function deleteAccount(expectedUserId: string): Promise<{ deleted: boolean; google_revocation: "revoked" | "unconfirmed" | "not_connected" }> {
  return apiFetch("/api/auth/account", {
    method: "DELETE",
    body: { confirmation: "DELETE", expected_user_id: expectedUserId },
    timeoutMs: 60000,
  });
}

export function importLocalData(): Promise<ImportLocalDto> {
  return apiFetch<ImportLocalDto>("/api/auth/import-local", { method: "POST" });
}

/** Redirect the browser to the backend Google Sign-In flow. */
export function beginGoogleSignIn(): void {
  window.location.assign(apiUrl("/api/auth/login"));
}

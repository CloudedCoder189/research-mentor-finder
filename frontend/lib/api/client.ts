import { AUTH_CHECK_EVENT } from "@/lib/auth-sync";

export type ApiErrorKind =
  | "unavailable"
  | "timeout"
  | "not-found"
  | "server"
  | "invalid"
  | "rate-limited"
  | "unauthorized"
  | "forbidden";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

let csrfToken: string | null = null;

/**
 * Sets the CSRF token the API client sends on non-GET requests. The backend
 * issues it as part of the session (GET /api/auth/me exposes it); without it,
 * state-changing requests are rejected with 403.
 */
export function setApiCsrfToken(token: string | null): void {
  csrfToken = token;
}

export async function apiFetch<T>(
  path: string,
  {
    method = "GET",
    body,
    timeoutMs = 15000,
    signal,
  }: {
    method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
    body?: unknown;
    timeoutMs?: number;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const onExternalAbort = () => controller.abort();
  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", onExternalAbort);
  }

  try {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

    const response = await fetch(apiUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
      credentials: "include",
    });

    if ((response.status === 401 || response.status === 403) && path !== "/api/auth/me") {
      window.dispatchEvent(new Event(AUTH_CHECK_EVENT));
    }
    if (response.status === 401) {
      throw new ApiError("unauthorized", "Sign in to continue.", 401);
    }
    if (response.status === 403) {
      throw new ApiError(
        "forbidden",
        "Your session could not verify this action. Please sign in again.",
        403,
      );
    }
    if (response.status === 404) {
      throw new ApiError("not-found", "The requested record was not found.", 404);
    }
    if (response.status === 422) {
      if (path === "/api/profile/resume-preview" || /^\/api\/outreach\/\d+\/follow-up-draft$/.test(path)) {
        const problem = await response.json().catch(() => null);
        if (typeof problem?.detail === "string") throw new ApiError("invalid", problem.detail, 422);
      }
      throw new ApiError("invalid", "The request was not valid.", 422);
    }
    if (response.status === 409) {
      throw new ApiError("invalid", "Your account or data changed. Reload before trying again.", 409);
    }
    if (response.status === 429) {
      const retrySeconds = Number(response.headers.get("Retry-After"));
      const wait = Number.isFinite(retrySeconds) && retrySeconds > 0
        ? ` Try again in ${Math.ceil(retrySeconds)} seconds.`
        : " Please try again later.";
      throw new ApiError("rate-limited", `Request limit reached.${wait}`, 429);
    }
    if (response.status === 503 && path === "/api/profile/resume-preview") {
      throw new ApiError("server", "Résumé processing is busy or unavailable. Please try again shortly.", 503);
    }
    if (!response.ok) {
      throw new ApiError("server", `The API returned HTTP ${response.status}.`, response.status);
    }
    return (await response.json()) as T;
  } catch (cause) {
    if (timedOut) {
      throw new ApiError("timeout", "The request took too long and was cancelled.", null);
    }
    if (cause instanceof ApiError) {
      throw cause;
    }
    throw new ApiError(
      "unavailable",
      "We could not connect to the research directory. Check your connection and try again shortly.",
      null,
    );
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }
}

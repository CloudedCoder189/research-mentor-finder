/** Non-identifying signals only: never publish a cookie, token or account ID. */
export const AUTH_CHANGE_KEY = "rmf-auth-change";
export const AUTH_CHECK_EVENT = "rmf-auth-check";

export function announceAuthChange(): void {
  try {
    window.localStorage.setItem(AUTH_CHANGE_KEY, `${Date.now()}:${Math.random()}`);
  } catch { /* Focus and visibility revalidation work without browser storage. */ }
}

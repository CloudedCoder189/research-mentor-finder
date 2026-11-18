// A profile can only return to a search on this site, never an external URL.
export function discoverReturn(value: string | string[] | undefined): string {
  if (typeof value !== "string" || !value.startsWith("/")) return "/discover";
  try {
    const url = new URL(value, "https://finder.invalid");
    if (url.origin !== "https://finder.invalid" || url.pathname !== "/discover") {
      return "/discover";
    }
    return url.pathname + url.search;
  } catch {
    return "/discover";
  }
}

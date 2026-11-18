"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { apiUrl } from "@/lib/api/client";

function category(path: string): string | null {
  const pages: Record<string, string> = {"/":"home", "/discover":"discover", "/for-you":"recommendations", "/saved":"saved", "/account":"account", "/account/onboarding":"profile_setup", "/outreach":"outreach", "/resources":"resources", "/start-research":"starter", "/opportunities":"pathways"};
  if (/^\/researchers\/\d+$/.test(path)) return "researcher";
  if (/^\/outreach\/compose\/\d+$/.test(path)) return "draft";
  return pages[path] ?? null;
}

export function PageViews() {
  const path = usePathname();
  const previous = useRef<string | null>(null);
  useEffect(() => {
    if (!path || previous.current === path) return;
    previous.current = path;
    const page = category(path);
    if (!page || navigator.doNotTrack === "1" || (navigator as Navigator & {globalPrivacyControl?: boolean}).globalPrivacyControl) return;
    void fetch(apiUrl("/api/usage/pageview"), {
      method: "POST", credentials: "omit", referrerPolicy: "no-referrer",
      headers: {"Content-Type":"application/json"}, body: JSON.stringify({page}),
      signal: AbortSignal.timeout(4000),
    }).catch(() => {});
  }, [path]);
  return null;
}

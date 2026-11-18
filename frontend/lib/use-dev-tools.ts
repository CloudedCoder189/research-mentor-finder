"use client";

import { useEffect, useState } from "react";

/**
 * Development-only UI (local dev-login buttons) stays reachable but is hidden from
 * the normal polished presentation. Opt in explicitly with `?devtools=1`.
 * This only gates visibility; auth behavior and the dev-login request are unchanged.
 */
export function useDevToolsVisible(): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      setVisible(params.get("devtools") === "1");
    } catch {
      setVisible(false);
    }
  }, []);

  return visible;
}

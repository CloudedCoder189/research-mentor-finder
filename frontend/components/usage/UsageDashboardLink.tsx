"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth-context";

export function UsageDashboardLink() {
  const { user } = useAuth();
  const userId = user?.user_id;
  const [owner, setOwner] = useState<string | null>(null);
  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    apiFetch<{ allowed: boolean }>("/api/usage/access", { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setOwner(result.allowed ? userId : null); })
      .catch(() => {});
    return () => controller.abort();
  }, [userId]);
  if (!userId || owner !== userId) return null;
  return <p className="mt-4 text-sm"><Link href="/account/usage" className="focus-ring rounded-control font-medium text-brand-700 underline">View private website usage</Link></p>;
}

"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { getGmailStatus } from "@/lib/api/gmail";

export function useGmailAvailability() {
  const { user } = useAuth();
  const userId = user?.user_id;
  const [connection, setConnection] = useState<{ userId: string; canSync: boolean } | null>(null);
  useEffect(() => {
    if (!userId) return;
    const controller = new AbortController();
    getGmailStatus(controller.signal).then(status => {
      if (!controller.signal.aborted) setConnection({ userId, canSync: Boolean(status.available && status.connected) });
    }).catch(() => { /* Default to manual planning when availability cannot be established. */ });
    return () => controller.abort();
  }, [userId]);
  return { canSync: Boolean(userId && connection?.userId === userId && connection.canSync) };
}

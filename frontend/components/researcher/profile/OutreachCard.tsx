"use client";

import { LogIn, NotebookPen, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ProfileSaveQueue } from "@/lib/profileSaveQueue";
import { useGmailAvailability } from "@/hooks/useGmailAvailability";
import { OutreachStatusBadge } from "@/components/researcher/OutreachStatusBadge";
import { Button } from "@/components/ui/Button";
import { Select, Textarea } from "@/components/ui/Input";
import { useAuth } from "@/lib/auth-context";
import { getOutreachFor, gmailSyncFor, toNumericId, updateOutreach } from "@/lib/api/outreach";
import { OUTREACH_STATUSES } from "@/lib/meta";
import type { OutreachStatus } from "@/types";

export function OutreachCard({ researcherId }: { researcherId: string }) {
  const { user } = useAuth();
  return <OutreachCardForUser key={`${user?.user_id}:${researcherId}`} researcherId={researcherId} />;
}

function OutreachCardForUser({ researcherId }: { researcherId: string }) {
  const { user, status: authStatus, signIn } = useAuth();
  const userId = user?.user_id;
  const { canSync } = useGmailAvailability();
  const numericId = toNumericId(researcherId);
  const [status, setStatus] = useState<OutreachStatus>("Not contacted");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const queue = useRef<ProfileSaveQueue<{ status: OutreachStatus; notes: string }> | null>(null);
  const editSequence = useRef(0);
  const currentEdit = useRef({ status: "Not contacted" as OutreachStatus, notes: "" });

  useEffect(() => {
    if (!userId || numericId === 0) return;
    let cancelled = false;
    const activeQueue = new ProfileSaveQueue<{ status: OutreachStatus; notes: string }>(async next => {
      await updateOutreach(numericId, { expected_user_id: userId, outreach_status: next.status, notes: next.notes });
    });
    queue.current = activeQueue;
    getOutreachFor(numericId)
      .then((dto) => {
        if (cancelled) return;
        setStatus(dto.outreach.status);
        setNotes(dto.outreach.notes);
        currentEdit.current = { status: dto.outreach.status, notes: dto.outreach.notes };
        setLoaded(true);
        setError(null);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Could not load outreach.");
        }
      });
    return () => {
      cancelled = true;
      activeQueue.flush();
      queue.current = null;
    };
  }, [userId, numericId, loadAttempt]);

  const persist = async (nextStatus: OutreachStatus, nextNotes: string) => {
    if (!userId || numericId === 0 || !loaded || !queue.current) return;
    const activeQueue = queue.current;
    const sequence = ++editSequence.current;
    currentEdit.current = { status: nextStatus, notes: nextNotes };
    setStatus(nextStatus);
    setNotes(nextNotes);
    setSaving(true);
    setError(null);
    const saved = await activeQueue.save(currentEdit.current);
    if (queue.current === activeQueue && sequence === editSequence.current) {
      setSaving(false);
      if (!saved) setError("Your latest notes could not be saved. Retry to keep your changes.");
    }
  };

  const runSync = async () => {
    if (!user || numericId === 0) return;
    setSyncing(true);
    setError(null);
    setSyncMessage(null);
    try {
      const result = await gmailSyncFor(numericId);
      setSyncMessage(result.message);
      if (result.outreach) {
        setStatus(result.outreach.outreach.status);
        setNotes(result.outreach.outreach.notes);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not check Gmail status.");
    } finally {
      setSyncing(false);
    }
  };

  if (authStatus === "loading") {
    return (
      <section className="card animate-pulse p-5" aria-hidden="true">
        <div className="h-4 w-1/2 rounded bg-slate-200" />
        <div className="mt-4 h-24 rounded bg-slate-200" />
      </section>
    );
  }

  if (!user) {
    return (
      <section className="card p-5" aria-labelledby="outreach-card-title">
        <h3
          id="outreach-card-title"
          className="inline-flex items-center gap-2 text-base font-semibold text-ink"
        >
          <NotebookPen className="h-4 w-4 text-brand-600" aria-hidden="true" />
          Outreach &amp; notes
        </h3>
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-500">Status:</span>
            <OutreachStatusBadge status="Not contacted" />
          </div>
          <div className="mt-4 rounded-control border border-border bg-slate-50 p-4">
            <p className="text-sm text-ink-600">Sign in to track outreach for this researcher.</p>
            <Button variant="secondary" size="sm" className="mt-3" onClick={signIn}>
              <LogIn className="h-3.5 w-3.5" aria-hidden="true" />
              Sign in
            </Button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="card p-5" aria-labelledby="outreach-card-title">
      <h3 id="outreach-card-title" className="inline-flex items-center gap-2 text-base font-semibold text-ink">
        <NotebookPen className="h-4 w-4 text-brand-600" aria-hidden="true" />
        Outreach &amp; notes
      </h3>
      <div className="mt-4 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-500">Status:</span>
          <OutreachStatusBadge status={status} />
          {canSync ? <Button
            variant="outline"
            size="sm"
            onClick={() => void runSync()}
            disabled={syncing || saving || !loaded || numericId === 0}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {syncing ? "Checking…" : "Check Gmail status"}
          </Button> : null}
        </div>
        {syncMessage ? <p className="text-sm text-emerald-700">{syncMessage}</p> : null}
        <Select
          id={`outreach-status-${researcherId}`}
          label="Update status"
          options={[...OUTREACH_STATUSES]}
          value={status}
          disabled={!loaded || syncing || numericId === 0}
          onChange={(event) => void persist(event.target.value as OutreachStatus, notes)}
        />
        <Textarea
          id={`outreach-notes-${researcherId}`}
          label="Private notes"
          rows={4}
          placeholder="Things to remember before reaching out…"
          value={notes}
          disabled={!loaded || syncing}
          onChange={(event) => void persist(status, event.target.value)}
        />
        {error ? <div role="alert"><p className="text-sm text-rose-600">{error}</p>
          <Button variant="secondary" size="sm" onClick={() => loaded
            ? void persist(currentEdit.current.status, currentEdit.current.notes)
            : setLoadAttempt(value => value + 1)}>Try again</Button></div> : null}
        <p className="text-xs text-slate-400">
          {saving ? "Saving…" : !loaded ? "Loading your notes…" : error ? "Changes not saved." : "Saved to your account — private to you."}
        </p>
      </div>
    </section>
  );
}

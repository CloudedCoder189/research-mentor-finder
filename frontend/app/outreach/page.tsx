"use client";

import {
  CalendarClock,
  Clock,
  Inbox,
  Mail,
  MailCheck,
  MailPlus,
  PartyPopper,
  RefreshCw,
  Sparkles,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { OutreachStatusBadge } from "@/components/researcher/OutreachStatusBadge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorHelp } from "@/components/ui/ErrorHelp";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { useGmailAvailability } from "@/hooks/useGmailAvailability";
import {
  followUpDraft,
  getOutreachRows,
  gmailSyncAll,
  gmailSyncFor,
  toNumericId,
  updateOutreach,
} from "@/lib/api/outreach";
import { toSavedResult } from "@/lib/api/map";
import type { OutreachStatus, SavedResult } from "@/types";

const DASHBOARD_KINDS: Array<"All" | OutreachStatus> = [
  "All",
  "Follow-up due",
  "Replied",
  "Meeting scheduled",
  "Drafted",
  "Sent",
  "Closed",
  "Not contacted",
];

function addDays(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function statusDetail(outreach: SavedResult["outreach"]): string {
  if (outreach.followUpDue && outreach.followUpDate) {
    return `Follow-up due on ${outreach.followUpDate}. Send a short, warm nudge.`;
  }
  if (outreach.status === "Sent") {
    return `Initial outreach sent. No reply recorded yet.`;
  }
  if (outreach.status === "Replied") {
    return `Reply received${outreach.gmailRepliedAt ? ` on ${outreach.gmailRepliedAt}` : ""}. Decide your next step.`;
  }
  if (outreach.status === "Meeting scheduled") {
    return `Meeting scheduled. Prepare a short agenda and questions.`;
  }
  if (outreach.status === "Follow-up due") {
    return `A follow-up is due. Draft a note to keep the conversation going.`;
  }
  if (outreach.status === "Drafted") {
    return `Draft in progress. Review it before anything else.`;
  }
  if (outreach.status === "Closed") {
    return `Conversation closed.`;
  }
  if (outreach.status === "Not contacted") {
    return `No outreach yet. Start with a personalized draft.`;
  }
  return outreach.notes || "No activity recorded yet.";
}

export default function OutreachPage() {
  const { canSync } = useGmailAvailability();
  const [active, setActive] = useState<"All" | OutreachStatus>("All");
  const [rows, setRows] = useState<SavedResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [syncInfo, setSyncInfo] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOutreachRows();
      setRows(data.results.map(toSavedResult));
      setError(null);
    } catch (cause) {
      setRows([]);
      setError(cause instanceof Error ? cause.message : "Could not load outreach.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const entries = useMemo(
    () => rows.filter((entry) => active === "All" || entry.outreach.status === active),
    [rows, active],
  );

  const counts = useMemo(() => {
    const map = new Map<OutreachStatus, number>();
    for (const entry of rows) {
      map.set(entry.outreach.status, (map.get(entry.outreach.status) ?? 0) + 1);
    }
    return map;
  }, [rows]);

  const patch = async (id: string, payload: Parameters<typeof updateOutreach>[1]) => {
    const numeric = toNumericId(id);
    if (numeric === 0) return;
    setPendingId(id);
    setNotice(null);
    try {
      const result = await updateOutreach(numeric, payload);
      const updated = toSavedResult(result);
      setRows((current) =>
        current.map((row) =>
          row.researcher.id === id ? updated : row,
        ),
      );
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not update outreach status.");
    } finally {
      setPendingId(null);
    }
  };

  const markStatus = (id: string, status: OutreachStatus) =>
    void patch(id, { outreach_status: status });

  const snooze = (id: string) =>
    void patch(id, { outreach_status: "Sent", follow_up_date: addDays(7) });

  const addFollowUp = (id: string) =>
    void patch(id, { outreach_status: "Follow-up due", follow_up_date: addDays(7) });

  const runSyncAll = async () => {
    if (syncingAll) return;
    setSyncingAll(true);
    setNotice(null);
    setSyncInfo(null);
    try {
      const result = await gmailSyncAll();
      if (result.checked === 0) {
        setSyncInfo("No Gmail-linked conversations to check yet.");
      } else {
        let summary = `Checked ${result.checked} ${result.checked === 1 ? "conversation" : "conversations"} against Gmail; ${result.updated} ${result.updated === 1 ? "record was" : "records were"} updated.`;
        if (result.errors.length === 1) {
          summary += " One check failed; see the row for details.";
        } else if (result.errors.length > 1) {
          summary += ` ${result.errors.length} checks failed; see the rows for details.`;
        }
        setSyncInfo(summary);
      }
      const data = await getOutreachRows();
      setRows(data.results.map(toSavedResult));
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not check Gmail status.");
    } finally {
      setSyncingAll(false);
    }
  };

  const runSyncFor = async (id: string) => {
    const numeric = toNumericId(id);
    if (numeric === 0) return;
    setPendingId(id);
    setNotice(null);
    setSyncInfo(null);
    try {
      const result = await gmailSyncFor(numeric);
      setSyncInfo(result.message);
      if (result.outreach) {
        const updated = toSavedResult(result.outreach);
        setRows((current) =>
          current.map((row) => (row.researcher.id === id ? updated : row)),
        );
      }
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not check this conversation in Gmail.");
    } finally {
      setPendingId(null);
    }
  };

  const runFollowUp = async (id: string) => {
    const numeric = toNumericId(id);
    if (numeric === 0) return;
    const row = rows.find(entry => entry.researcher.id === id);
    if (!row?.outreach.emailSentAt && !row?.outreach.gmailSentAt) {
      setNotice("Add the date you sent this email below before drafting a follow-up.");
      return;
    }
    setPendingId(id);
    setNotice(null);
    setSyncInfo(null);
    try {
      const result = await followUpDraft(numeric);
      setSyncInfo(result.message);
      const updated = toSavedResult(result.outreach);
      setRows((current) =>
        current.map((row) => (row.researcher.id === id ? updated : row)),
      );
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Could not draft the follow-up.");
    } finally {
      setPendingId(null);
    }
  };

  return (
    <RequireAuth>
      <Container className="py-10 sm:py-12">
      <PageHeader
        title="Your drafts and outreach"
        description="Follow-ups, replies, and next steps — all in one place."
      />

      <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500" aria-live="polite">
        <span className="font-semibold text-ink-950">{rows.length}</span>{" "}
        {rows.length === 1 ? "researcher tracked" : "researchers tracked"}
        <span aria-hidden="true">·</span>
        <span className="font-semibold text-ink-950">{counts.get("Replied") ?? 0}</span>{" "}
        {counts.get("Replied") === 1 ? "reply" : "replies"} to review
        <span aria-hidden="true">·</span>
        <span className="font-semibold text-ink-950">{counts.get("Follow-up due") ?? 0}</span>{" "}
        follow-up{counts.get("Follow-up due") === 1 ? "" : "s"} due
        <span aria-hidden="true">·</span>
        <span className="font-semibold text-ink-950">{counts.get("Meeting scheduled") ?? 0}</span>{" "}
        meeting{counts.get("Meeting scheduled") === 1 ? "" : "s"} scheduled
      </p>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-500">
          Update your outreach status manually{canSync ? ", or check Gmail for linked conversations" : ""}. Nothing is ever sent automatically.
        </p>
        {canSync ? <Button variant="secondary" size="sm" onClick={() => void runSyncAll()} disabled={syncingAll}>
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {syncingAll ? "Checking…" : "Check Gmail status"}
        </Button> : null}
      </div>

      <div className="mt-6 flex flex-wrap gap-2" role="tablist" aria-label="Outreach status">
        {DASHBOARD_KINDS.map((kind) => {
          const label = kind === "All" ? "All" : kind;
          const count = kind === "All" ? rows.length : (counts.get(kind) ?? 0);
          if (kind !== "All" && count === 0) return null;
          return (
            <button
              key={kind}
              type="button"
              role="tab"
              aria-selected={active === kind}
              onClick={() => setActive(kind)}
              className={
                "focus-ring inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-sm font-medium transition-colors " +
                (active === kind
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-border bg-surface text-ink-600 hover:bg-slate-50")
              }
            >
              {label}
              <span className={active === kind ? "text-brand-100" : "text-slate-400"}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <p className="mt-4 text-sm text-slate-500" aria-live="polite">
        {entries.length} {entries.length === 1 ? "tracked researcher" : "tracked researchers"}
        {active !== "All" ? <> in “{active}”</> : null}
      </p>

      {notice ? <p className="mt-3 text-sm text-rose-600" role="alert">{notice}</p> : null}
      {syncInfo ? <p className="mt-3 text-sm text-emerald-700">{syncInfo}</p> : null}

      {loading ? (
        <div className="card mt-6 animate-pulse p-5" aria-hidden="true">
          <div className="h-4 w-2/3 rounded bg-slate-200" />
          <div className="mt-4 h-4 w-1/2 rounded bg-slate-200" />
        </div>
      ) : error ? (
        <div className="card mt-6 p-6" role="alert">
          <div className="flex items-start gap-3">
            <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
            <div>
              <h2 className="text-base font-semibold text-ink">Outreach is unavailable</h2>
              <p className="mt-1 text-sm text-slate-500">{error}</p>
              <ErrorHelp />
              <div className="mt-4">
                <Button variant="secondary" onClick={() => void load()}>
                  Try again
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" aria-hidden="true" />}
          title="Nothing here yet"
          description="Draft your first email to a saved researcher to see it appear here."
          action={<LinkButton href="/saved">Go to Saved</LinkButton>}
        />
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {entries.map(({ researcher, outreach }) => (
            <section
              key={researcher.id}
              className="card p-4 sm:p-5"
              aria-label={`${researcher.name} outreach`}
            >
              <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-stretch lg:gap-5">
                <div className="lg:col-span-5">
                  <div className="flex min-h-full flex-col gap-3">
                    <OutreachStatusBadge status={outreach.status} />
                    <div>
                      <h3 className="text-base font-semibold text-ink-950">
                        <a
                          href={`/researchers/${researcher.id}`}
                          className="hover:text-brand-700 hover:underline"
                        >
                          {researcher.name}
                        </a>
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">
                        {researcher.title} · {researcher.department}, {researcher.university}
                      </p>
                    </div>
                    {outreach.notes ? (
                      <p className="text-sm text-ink-600">
                        <span className="text-slate-400">Note: </span>
                        {outreach.notes}
                      </p>
                    ) : null}
                  </div>
                </div>

                <div className="lg:col-span-4">
                  <div className="panel-aqua flex h-full flex-col gap-2 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-accent-700">
                      Current status
                    </p>
                    <p className="text-sm leading-relaxed text-ink-700">
                      {statusDetail(outreach)}
                    </p>
                    <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                      {outreach.followUpDue && outreach.followUpDate ? (
                        <li className="inline-flex items-center gap-1 text-amber-700">
                          <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
                          Follow-up due {outreach.followUpDate}
                        </li>
                      ) : null}
                      {!outreach.followUpDue && outreach.followUpDate && outreach.status === "Sent" ? (
                        <li className="inline-flex items-center gap-1">
                          <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
                          Follow-up {outreach.followUpDate}
                        </li>
                      ) : null}
                      {outreach.emailSentAt ? (
                        <li className="inline-flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                          Sent {outreach.emailSentAt}
                        </li>
                      ) : null}
                      {outreach.gmailRepliedAt ? (
                        <li className="inline-flex items-center gap-1 text-emerald-700">
                          <MailCheck className="h-3.5 w-3.5" aria-hidden="true" />
                          Replied {outreach.gmailRepliedAt}
                        </li>
                      ) : null}
                      {outreach.gmailLastCheckedAt ? (
                        <li className="inline-flex items-center gap-1">
                          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                          Checked {outreach.gmailLastCheckedAt}
                        </li>
                      ) : null}
                    </ul>
                  </div>
                </div>

                <div className="lg:col-span-3">
                  <div className="flex h-full flex-wrap items-center gap-2 lg:flex-col lg:flex-nowrap lg:items-start">
                    <div className="flex flex-wrap items-center gap-2 lg:w-full">
                      {canSync ? <Button
                        variant="outline"
                        size="sm"
                        disabled={pendingId === researcher.id}
                        onClick={() => void runSyncFor(researcher.id)}
                      >
                        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                        Check Gmail
                      </Button> : null}
                      <ContextActions
                        status={outreach.status}
                        researcherId={researcher.id}
                        pending={pendingId === researcher.id}
                        onMark={markStatus}
                        onSnooze={snooze}
                        onAddFollowUp={addFollowUp}
                        onFollowUp={runFollowUp}
                      />
                      {(outreach.status === "Sent" || outreach.status === "Follow-up due") ? (
                        <div className="w-full"><Input id={`sent-date-${researcher.id}`} label="Date you sent the email" type="date"
                          value={outreach.emailSentAt?.slice(0, 10) || ""} disabled={pendingId === researcher.id}
                          onChange={event => void patch(researcher.id, { email_sent_at: event.target.value })} />
                          {!outreach.emailSentAt && !outreach.gmailSentAt ? <p className="mt-1 text-xs text-slate-500">Confirm a sent date to prepare a follow-up.</p> : null}</div>
                      ) : null}
                      <LinkButton href={`/researchers/${researcher.id}`} variant="secondary" size="sm">
                        View profile
                      </LinkButton>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          ))}
          <p className="mt-6 border-t border-border pt-5 text-center text-xs text-slate-400">
            One thoughtful message at a time. Review every draft before sending.
          </p>
        </div>
      )}
      </Container>
    </RequireAuth>
  );
}

function ContextActions({
  status,
  researcherId,
  pending,
  onMark,
  onSnooze,
  onAddFollowUp,
  onFollowUp,
}: {
  status: OutreachStatus;
  researcherId: string;
  pending: boolean;
  onMark: (id: string, status: OutreachStatus) => void;
  onSnooze: (id: string) => void;
  onAddFollowUp: (id: string) => void;
  onFollowUp: (id: string) => void;
}) {
  switch (status) {
    case "Drafted":
      return (
        <LinkButton href={`/outreach/compose/${researcherId}`} size="sm">
          <Mail className="h-3.5 w-3.5" aria-hidden="true" />Continue draft
        </LinkButton>
      );
    case "Follow-up due":
      return (
        <>
          <LinkButton href={`/outreach/compose/${researcherId}`} size="sm">
            <Mail className="h-3.5 w-3.5" aria-hidden="true" />
            Continue draft
          </LinkButton>
          <Button
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => void onFollowUp(researcherId)}
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Draft follow-up
          </Button>
          <Button variant="secondary" size="sm" disabled={pending} onClick={() => onSnooze(researcherId)}>
            Snooze
          </Button>
        </>
      );
    case "Sent":
      return (
        <>
          <Button
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => onMark(researcherId, "Replied")}
          >
            <MailCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Log reply
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => void onFollowUp(researcherId)}
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Draft follow-up
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => onAddFollowUp(researcherId)}
          >
            <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
            Add follow-up
          </Button>
        </>
      );
    case "Replied":
      return (
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={() => onMark(researcherId, "Meeting scheduled")}
        >
          <PartyPopper className="h-3.5 w-3.5" aria-hidden="true" />
          Schedule meeting
        </Button>
      );
    case "Meeting scheduled":
      return (
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={() => onMark(researcherId, "Closed")}
        >
          Mark closed
        </Button>
      );
    case "Closed":
      return (
        <Button
          variant="secondary"
          size="sm"
          disabled={pending}
          onClick={() => onMark(researcherId, "Replied")}
        >
          Reopen
        </Button>
      );
    default:
      return (
        <LinkButton href={`/outreach/compose/${researcherId}`} size="sm">
          <MailPlus className="h-3.5 w-3.5" aria-hidden="true" />
          Start outreach
        </LinkButton>
      );
  }
}

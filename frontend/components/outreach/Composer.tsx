"use client";

import {
  ArrowLeft,
  Copy,
  ExternalLink,
  Eye,
  LogOut,
  Mail,
  Save,
  Sparkles,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { OutreachStatusBadge } from "@/components/researcher/OutreachStatusBadge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { ErrorHelp } from "@/components/ui/ErrorHelp";
import { InlineNotice, Input, Select, Textarea } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  beginGmailConnect,
  createGmailDraft,
  disconnectGmail,
  getGmailStatus,
  updateGmailDraft,
} from "@/lib/api/gmail";
import { toProfileResearcher } from "@/lib/api/map";
import { getOutreachFor, toNumericId, updateOutreach } from "@/lib/api/outreach";
import { getResearcherProfile } from "@/lib/api/researchers";
import { buildOutreachDraft } from "@/lib/outreachDraft";
import { OUTREACH_STATUSES } from "@/lib/meta";
import { useStudentProfile } from "@/lib/useStudentProfile";
import type { GmailDraftResultDto, GmailStatusDto } from "@/lib/api/types";
import type { OutreachStatus, Researcher } from "@/types";

export function LiveComposer({ researcherId }: { researcherId: string }) {
  const { user } = useAuth();
  return <ComposerForUser key={`${user?.user_id}:${researcherId}`} researcherId={researcherId} />;
}

function ComposerForUser({ researcherId }: { researcherId: string }) {
  const { user } = useAuth();
  const userId = user?.user_id;
  const recoveryKey = userId ? `rmf-unsaved-draft:${userId}:${researcherId}` : null;
  const { profile, hydrated } = useStudentProfile();
  const numericId = toNumericId(researcherId);

  const [researcher, setResearcher] = useState<Researcher | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadRetry, setLoadRetry] = useState(0);

  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState<OutreachStatus>("Not contacted");
  const [notes, setNotes] = useState("");
  const [restoredDraft, setRestoredDraft] = useState(false);
  const [dirty, setDirty] = useState(false);
  const latestDraft = useRef({ to: "", subject: "", body: "", notes: "" });
  useLayoutEffect(() => { latestDraft.current = { to, subject, body, notes }; }, [to, subject, body, notes]);

  const editDraft = (field: "to" | "subject" | "body" | "notes", value: string) => {
    const next = { ...latestDraft.current, [field]: value };
    latestDraft.current = next;
    ({ to: setTo, subject: setSubject, body: setBody, notes: setNotes }[field])(value);
    setDirty(true);
    setSavedMessage(null);
    if (recoveryKey) {
      try { window.sessionStorage.setItem(recoveryKey, JSON.stringify(next)); } catch { /* Navigation warning still protects edits. */ }
    }
  };

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const warnNavigation = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target === "_blank" || link.hasAttribute("download")) return;
      if (link.href === window.location.href) return;
      if (!window.confirm("This draft has unsaved changes. Leave without saving to your account?")) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", warnNavigation, true);
    return () => { window.removeEventListener("beforeunload", warn); document.removeEventListener("click", warnNavigation, true); };
  }, [dirty]);

  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const previewButton = useRef<HTMLButtonElement>(null);
  const previewPanel = useRef<HTMLDivElement>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  const [gmail, setGmail] = useState<GmailStatusDto | null>(null);
  const [gmailBusy, setGmailBusy] = useState(false);
  const [gmailError, setGmailError] = useState<string | null>(null);
  const [gmailNotice, setGmailNotice] = useState<string | null>(null);
  const [gmailDraftId, setGmailDraftId] = useState("");
  const [gmailAccount, setGmailAccount] = useState("");
  const [syncedContent, setSyncedContent] = useState<{ to: string; subject: string; body: string } | null>(null);

  useEffect(() => {
    if (previewing) previewPanel.current?.focus();
  }, [previewing]);

  const closePreview = () => {
    setPreviewing(false);
    previewButton.current?.focus();
  };

  useEffect(() => {
    if (!userId) return;
    if (numericId === 0) {
      setLoading(false);
      setLoadError("This researcher is not in the directory.");
      return;
    }
    let cancelled = false;
    Promise.all([getResearcherProfile(researcherId), getOutreachFor(numericId)])
      .then(([profileDto, outreachDto]) => {
        if (cancelled) return;
        const researcher = toProfileResearcher(profileDto);
        const outreach = outreachDto.outreach;
        setResearcher(researcher);
        setStatus(outreach.status);
        setNotes(outreach.notes);
        setTo(outreach.email_to || researcher.email);
        if (outreach.email_subject || outreach.email_body) {
          setSubject(outreach.email_subject);
          setBody(outreach.email_body);
          setRestoredDraft(true);
        }
        if (recoveryKey) {
          try {
            const recovered = JSON.parse(window.sessionStorage.getItem(recoveryKey) || "null");
            if (recovered && ["to", "subject", "body", "notes"].every(key => typeof recovered[key] === "string")) {
              setTo(recovered.to); setSubject(recovered.subject); setBody(recovered.body); setNotes(recovered.notes);
              setRestoredDraft(true); setDirty(true);
              setSavedMessage("Recovered unsaved edits from this tab. Save draft to keep them in your account.");
            }
          } catch { /* Ignore unavailable or malformed tab recovery. */ }
        }
        setGmailDraftId(outreach.gmail_draft_id);
        setGmailAccount(outreach.gmail_account_email);
        if (outreach.gmail_draft_id && (outreach.email_subject || outreach.email_body)) {
          setSyncedContent({
            to: outreach.email_to,
            subject: outreach.email_subject,
            body: outreach.email_body,
          });
        }
        setLoadError(null);
      })
      .catch((cause) => {
        if (cancelled) return;
        setLoadError(cause instanceof Error ? cause.message : "Could not load this researcher.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [researcherId, numericId, loadRetry, userId, recoveryKey]);

  useEffect(() => {
    let cancelled = false;
    getGmailStatus()
      .then((status) => {
        if (!cancelled) setGmail(status);
      })
      .catch((cause) => {
        if (!cancelled) {
          setGmail(null);
          setGmailError(cause instanceof Error ? cause.message : "Could not check Gmail connection.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hydrated || !researcher || restoredDraft) return;
    const draft = buildOutreachDraft(researcher, profile);
    setTo((current) => current || researcher.email);
    setSubject((current) => current || draft.subject);
    setBody((current) => current || draft.body);
  }, [hydrated, researcher, profile, restoredDraft]);

  const saveDraft = async () => {
    if (numericId === 0 || !researcher) return;
    setSaving(true);
    setSavedMessage(null);
    setSaveError(null);
    const savedSnapshot = { to, subject, body, notes };
    try {
      const result = await updateOutreach(numericId, {
        expected_user_id: userId,
        outreach_status: status === "Not contacted" ? "Drafted" : status,
        email_to: to,
        email_subject: subject,
        email_body: body,
        notes,
      });
      setStatus(result.outreach.status);
      setRestoredDraft(true);
      if (JSON.stringify(latestDraft.current) === JSON.stringify(savedSnapshot)) {
        setDirty(false);
        if (recoveryKey) { try { window.sessionStorage.removeItem(recoveryKey); } catch { /* Optional recovery storage. */ } }
        setSavedMessage("Draft saved to your records.");
      } else {
        setSavedMessage("Earlier draft saved. Your latest edits are still unsaved.");
      }
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "Could not save the draft.");
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (next: OutreachStatus) => {
    if (numericId === 0) return;
    setStatus(next);
    setSavedMessage(null);
    setSaveError(null);
    try {
      const result = await updateOutreach(numericId, { outreach_status: next });
      setStatus(result.outreach.status);
      setSavedMessage(`Status updated to “${result.outreach.status}”.`);
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "Could not update the status.");
    }
  };

  const draftingContext = useMemo(() => {
    if (!researcher) return { topics: [], interests: [], skills: [] };
    return {
      topics: researcher.topics.slice(0, 4),
      interests: profile.interests.slice(0, 3),
      skills: profile.skills.slice(0, 3),
    };
  }, [researcher, profile]);

  const statusUpdating = saving || loading;

  async function copyDraft(part: "subject" | "message") {
    setCopyNotice(null);
    try {
      await navigator.clipboard.writeText(part === "subject" ? subject : body);
      setCopyNotice(`${part === "subject" ? "Subject" : "Message"} copied. Paste it into your email app and review before sending.`);
    } catch {
      const field = document.getElementById(part === "subject" ? "compose-subject" : "compose-body") as HTMLInputElement | HTMLTextAreaElement | null;
      field?.focus();
      field?.select();
      setCopyNotice("Your browser blocked clipboard access. The text is selected; copy it manually.");
    }
  }

  const isGmailUnsynced = Boolean(
    syncedContent &&
      (to !== syncedContent.to || subject !== syncedContent.subject || body !== syncedContent.body),
  );

  const connectGmail = async () => {
    setGmailBusy(true);
    setGmailError(null);
    try {
      const { auth_url } = await beginGmailConnect();
      window.location.assign(auth_url);
    } catch (cause) {
      setGmailError(cause instanceof Error ? cause.message : "Could not start Gmail connection.");
    } finally {
      setGmailBusy(false);
    }
  };

  const refreshAfterGmailFailure = async () => {
    if (numericId === 0) return;
    try {
      const result = await getOutreachFor(numericId);
      setStatus(result.outreach.status);
      setNotes(result.outreach.notes);
    } catch {
      // Keep current composer state; the next save re-syncs.
    }
  };

  const applyGmailResult = (
    result: GmailDraftResultDto,
    sent: { to: string; subject: string; body: string },
  ) => {
    setGmailDraftId(result.gmail_draft_id);
    setGmailAccount(result.gmail_account_email);
    setSyncedContent(sent);
    setStatus(result.outreach.outreach.status);
    setNotes(result.outreach.outreach.notes);
  };

  const runCreateGmailDraft = async () => {
    if (numericId === 0) return;
    setGmailBusy(true);
    setGmailError(null);
    setGmailNotice(null);
    const payload = { to, subject, body, notes };
    try {
      const result = await createGmailDraft(numericId, payload);
      applyGmailResult(result, { to, subject, body });
      setGmailNotice("Gmail draft created. Open it in Gmail to review — nothing is sent automatically.");
    } catch (cause) {
      setGmailError(cause instanceof Error ? cause.message : "Could not create the Gmail draft.");
      await refreshAfterGmailFailure();
    } finally {
      setGmailBusy(false);
    }
  };

  const runUpdateGmailDraft = async () => {
    if (numericId === 0) return;
    setGmailBusy(true);
    setGmailError(null);
    setGmailNotice(null);
    const payload = { to, subject, body, notes };
    try {
      const result = await updateGmailDraft(numericId, payload);
      applyGmailResult(result, { to, subject, body });
      setGmailNotice("Gmail draft updated — changed there, nothing was sent.");
    } catch (cause) {
      setGmailError(cause instanceof Error ? cause.message : "Could not update the Gmail draft.");
      await refreshAfterGmailFailure();
    } finally {
      setGmailBusy(false);
    }
  };

  const runDisconnectGmail = async () => {
    setGmailBusy(true);
    setGmailError(null);
    try {
      const removed = await disconnectGmail();
      if (removed.disconnected) {
        setGmail(null);
        setGmailNotice(removed.revocation === "unconfirmed"
          ? "Gmail disconnected from this app. Google did not confirm permission removal; remove Research Mentor Finder access in your Google Account connections."
          : "Gmail disconnected from this app.");
      }
    } catch (cause) {
      setGmailError(cause instanceof Error ? cause.message : "Could not disconnect Gmail.");
    } finally {
      setGmailBusy(false);
    }
  };

  return (
    <Container className="py-10 sm:py-12">
      <Link
        href="/outreach"
        className="focus-ring inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Outreach
      </Link>

      <div className="mt-4">
        <PageHeader
          title={researcher ? `Outreach to ${researcher.name}` : "Compose outreach email"}
          description={
            researcher
              ? `${researcher.university} · ${researcher.department}. Edit anything below to make it yours.`
              : "Loading this researcher from the directory…"
          }
          actions={
            researcher ? (
              <span className="inline-flex items-center gap-2">
                <OutreachStatusBadge status={status} />
              </span>
            ) : (
              undefined
            )
          }
        />
      </div>

      {loading ? (
        <div className="card mt-8 animate-pulse p-6" aria-hidden="true">
          <div className="h-4 w-1/3 rounded bg-slate-200" />
          <div className="mt-4 h-24 w-full rounded bg-slate-200" />
          <div className="mt-4 h-24 w-full rounded bg-slate-200" />
        </div>
      ) : loadError || !researcher ? (
        <div className="card mt-8 p-6" role="alert">
          <div className="flex items-start gap-3">
            <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
            <div>
              <h2 className="text-base font-semibold text-ink">Composer is unavailable</h2>
              <p className="mt-1 text-sm text-slate-500">
                {loadError ??
                  "This researcher could not be loaded. They may no longer be in the directory."}
              </p>
              <ErrorHelp />
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => { setLoading(true); setLoadError(null); setLoadRetry(value => value + 1); }}>
                  Try again
                </Button>
                <LinkButton variant="secondary" href="/outreach">
                  Back to Outreach
                </LinkButton>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            {restoredDraft ? (
              <InlineNotice tone="brand">
                Your saved draft was restored. Anything you save now updates these records.
              </InlineNotice>
            ) : null}
            <p className="text-sm text-slate-500">Before sending, confirm your education level in your profile, add your name, and replace generic wording with a genuine question about a source you have read. Check any location or time constraints yourself; this draft does not establish availability.</p>
            <div className="card p-5 sm:p-6" aria-label="Email form">
              <div className="space-y-5">
                <div>
                  <label htmlFor="compose-to" className="field-label">
                    To
                  </label>
                  <Input
                    id="compose-to"
                    type="email"
                    value={to}
                    onChange={(event) => editDraft("to", event.target.value)}
                    className="border-brand-200"
                  />
                </div>
                <Input
                  id="compose-subject"
                  label="Subject"
                  value={subject}
                  onChange={(event) => editDraft("subject", event.target.value)}
                />
                <Textarea
                  id="compose-body"
                  label="Message"
                  rows={12}
                  value={body}
                  onChange={(event) => editDraft("body", event.target.value)}
                />

                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
                  <Button type="button" variant="secondary" onClick={() => void copyDraft("subject")} disabled={!subject.trim()}>
                    <Copy className="h-4 w-4" aria-hidden="true" />Copy subject
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => void copyDraft("message")} disabled={!body.trim()}>
                    <Copy className="h-4 w-4" aria-hidden="true" />Copy message
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => void saveDraft()} disabled={saving}>
                    <Save className="h-4 w-4" aria-hidden="true" />
                    {saving ? "Saving…" : "Save draft"}
                  </Button>
                  <Button type="button" variant="secondary" onClick={(event) => {
                    previewButton.current = event.currentTarget;
                    setPreviewing(true);
                  }}>
                    <Eye className="h-4 w-4" aria-hidden="true" />
                    Preview email
                  </Button>
                  {gmail?.connected ? (
                    gmailDraftId ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void runUpdateGmailDraft()}
                        disabled={gmailBusy}
                      >
                        <Mail className="h-4 w-4" aria-hidden="true" />
                        {gmailBusy ? "Updating…" : "Update Gmail draft"}
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void runCreateGmailDraft()}
                        disabled={gmailBusy}
                      >
                        <Mail className="h-4 w-4" aria-hidden="true" />
                        {gmailBusy ? "Creating…" : "Create Gmail draft"}
                      </Button>
                    )
                  ) : gmail?.available ? (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void connectGmail()}
                      disabled={gmailBusy}
                    >
                      <Mail className="h-4 w-4" aria-hidden="true" />
                      {gmailBusy ? "Starting…" : "Connect Gmail"}
                    </Button>
                  ) : null}
                </div>

                {gmail?.connected && gmailAccount ? (
                  <p className="text-xs text-slate-400">
                    Drafting as {gmailAccount}. Nothing is sent automatically — review in Gmail first.
                  </p>
                ) : null}

                {copyNotice ? <p className="text-sm text-ink-600" role="status">{copyNotice}</p> : null}
                {dirty ? <p className="text-sm text-amber-700" role="status">Unsaved changes. Save draft to keep them in your account. Edits can be recovered in this tab.</p> : null}
                {isGmailUnsynced ? (
                  <InlineNotice tone="amber">
                    Local changes have not been synced. Save your draft or update the Gmail draft to sync.
                  </InlineNotice>
                ) : null}
                {gmailNotice ? <InlineNotice>{gmailNotice}</InlineNotice> : null}
                {saveError ? <InlineNotice tone="amber">{saveError}</InlineNotice> : null}
                {gmailError ? <InlineNotice tone="amber">{gmailError}</InlineNotice> : null}
                {savedMessage ? <InlineNotice>{savedMessage}</InlineNotice> : null}
              </div>
            </div>

            {previewing ? (
              <div ref={previewPanel} tabIndex={-1} className="card focus-ring min-w-0 p-5 [overflow-wrap:anywhere]" aria-label="Email preview" role="dialog" aria-modal="false"
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    closePreview();
                  }
                }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold text-ink">Preview</h3>
                  <button
                    type="button"
                    className="focus-ring rounded-control px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100"
                    onClick={closePreview}
                  >
                    Close
                  </button>
                </div>
                <dl className="mt-3 space-y-1 border-b border-border pb-3 text-sm">
                  <div className="flex gap-2">
                    <dt className="w-14 shrink-0 text-slate-500">To</dt>
                    <dd className="break-all text-ink-600">{to || "—"}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-14 shrink-0 text-slate-500">Subject</dt>
                    <dd className="min-w-0 text-ink-600">{subject}</dd>
                  </div>
                </dl>
                <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-600">{body}</p>
              </div>
            ) : null}
          </div>

          <aside className="space-y-6">
            <section className="card p-5" aria-labelledby="drafting-context-title">
              <h2 id="drafting-context-title" className="inline-flex items-center gap-2 text-base font-semibold text-ink">
                <Sparkles className="h-4 w-4 text-brand-600" aria-hidden="true" />
                Context for your draft
              </h2>
              <p className="mt-3 text-sm text-ink-600">
                Details from the researcher and your profile. Include relevant details in your message and review it before sending.
              </p>
              <dl className="mt-3 space-y-3 text-sm">
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Their research
                  </dt>
                  <dd className="mt-1.5 flex flex-wrap gap-1.5">
                    {draftingContext.topics.map((topic) => (
                      <span key={topic} className="chip-light">
                        {topic}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Your interests
                  </dt>
                  <dd className="mt-1.5 flex flex-wrap gap-1.5">
                    {draftingContext.interests.length === 0 ? <span className="text-slate-500">None added to your profile</span> : null}
                    {draftingContext.interests.map((interest) => (
                      <span key={interest} className="rounded-pill border border-brand-200 bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
                        {interest}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Your skills
                  </dt>
                  <dd className="mt-1.5 flex flex-wrap gap-1.5">
                    {draftingContext.skills.length === 0 ? <span className="text-slate-500">None added to your profile</span> : null}
                    {draftingContext.skills.map((skill) => (
                      <span key={skill} className="chip-aqua">
                        {skill}
                      </span>
                    ))}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="card p-5" aria-labelledby="outreach-status-title">
              <h2 id="outreach-status-title" className="text-base font-semibold text-ink">
                Outreach status
              </h2>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <OutreachStatusBadge status={status} />
              </div>
              <Select
                id="composer-status"
                label="Update status"
                options={[...OUTREACH_STATUSES]}
                value={status}
                disabled={statusUpdating}
                onChange={(event) => void updateStatus(event.target.value as OutreachStatus)}
              />
              <Textarea
                id="composer-notes"
                label="Private notes"
                rows={4}
                placeholder="Anything to remember…"
                value={notes}
                onChange={(event) => editDraft("notes", event.target.value)}
              />
              <p className="mt-2 text-xs text-slate-400">
                Notes and status are private to you and are saved with the draft.
              </p>
            </section>

            {gmail?.available || gmail?.connected ? <section className="card p-5" aria-labelledby="gmail-connection-title">
              <h2 id="gmail-connection-title" className="text-base font-semibold text-ink">
                Gmail draft
              </h2>
              {gmail?.connected ? (
                <div className="mt-3 space-y-3 text-sm">
                  <p className="text-slate-600">
                    Drafting as{" "}
                    <span className="break-all font-medium text-ink">
                      {gmail.account_email || "your Gmail account"}
                    </span>
                    .
                  </p>
                  {gmailDraftId ? (
                    <LinkButton
                      variant="outline"
                      href={gmail.draft_url}
                      target="_blank"
                      rel="noreferrer"
                      className="w-full"
                    >
                      <ExternalLink className="h-4 w-4" aria-hidden="true" />
                      Open in Gmail
                    </LinkButton>
                  ) : null}
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void runDisconnectGmail()}
                    disabled={gmailBusy}
                    className="w-full"
                  >
                    <LogOut className="h-4 w-4" aria-hidden="true" />
                    Disconnect Gmail
                  </Button>
                </div>
              ) : gmail?.available ? (
                <div className="mt-3 space-y-3 text-sm">
                  <p className="text-slate-600">
                    Connect Gmail to create a real draft you can review and send from your own
                    account. Nothing is sent automatically.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void connectGmail()}
                    disabled={gmailBusy}
                    className="w-full"
                  >
                    <Mail className="h-4 w-4" aria-hidden="true" />
                    Connect Gmail
                  </Button>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-600">Gmail connection is unavailable in this release. Save your draft here, or copy the subject and message into your email app.</p>
              )}
            </section> : <p className="text-sm text-slate-500">Save your draft here, then copy the subject and message into your email app. Sending is always your choice.</p>}
          </aside>
        </div>
      )}
      <p className="mt-6 border-t border-border pt-5 text-center text-xs text-slate-400">
        One thoughtful message at a time. Review every draft before sending.
      </p>
    </Container>
  );
}

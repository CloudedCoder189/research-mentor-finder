"use client";

import { useRouter } from "next/navigation";
import { GraduationCap, HardDriveDownload, Send, UserRound } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { ClearResearchProfile } from "@/components/profile/ClearResearchProfile";
import { ResumeImport } from "@/components/profile/ResumeImport";
import { ProfileSummary } from "@/components/researcher/ProfileSummary";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";
import { deleteAccount, importLocalData } from "@/lib/api/auth";
import { clearDraftRecovery } from "@/lib/draftRecovery";
import { useAuth } from "@/lib/auth-context";
import { useStudentProfile } from "@/lib/useStudentProfile";
import { UsageDashboardLink } from "@/components/usage/UsageDashboardLink";

export default function AccountPage() {
  const { profile, saveProfile, hydrated, saving, saveError, retryLoad } = useStudentProfile();
  const { user, localImportAvailable } = useAuth();
  const router = useRouter();
  const [resumeVersion, setResumeVersion] = useState(0);
  const [importing, setImporting] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteIdentity, setDeleteIdentity] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const query = useSyncExternalStore(
    callback => { window.addEventListener("popstate", callback); return () => window.removeEventListener("popstate", callback); },
    () => window.location.search,
    () => "",
  );
  const params = new URLSearchParams(query);
  const deletedNotice = params.get("deleted") === "1"
    ? params.get("google_revocation") === "unconfirmed"
      ? "Your account and stored Gmail credentials were deleted. Google access revocation could not be confirmed. Remove Research Mentor Finder from your Google Account connections to finish disconnecting."
      : "Your account was deleted. Your existing Gmail messages and drafts were not changed."
    : null;

  const runDelete = async () => {
    if (!user || user.user_id !== deleteIdentity || confirmation !== "DELETE" || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await deleteAccount(deleteIdentity);
      clearDraftRecovery();
      try { window.localStorage.removeItem(`rmf:profile:resume:${user.user_id}`); } catch { /* storage unavailable */ }
      // Reload the document so deleted profile/Saved state leaves memory too.
      const destination = new URL("/account", window.location.origin);
      destination.searchParams.set("deleted", "1");
      destination.searchParams.set("google_revocation", result.google_revocation);
      window.location.assign(destination.href);
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "Deletion did not finish. Try again.");
      setDeleting(false);
    }
  };

  const runImport = async () => {
    setImporting(true);
    setImportNotice(null);
    try {
      const result = await importLocalData();
      if (result.already_imported) {
        setImportNotice(
          "Local data was already imported to this account. Nothing changed.",
        );
      } else {
        const rows = result.imported_outreach_rows;
        setImportNotice(
          `Imported ${rows} local outreach ${
            rows === 1 ? "record" : "records"
          }${result.imported_gmail_tokens ? " and your Gmail connection" : ""} to this account.`,
        );
      }
    } catch (cause) {
      setImportNotice(cause instanceof Error ? cause.message : "Could not import local data.");
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
    {deletedNotice ? <Container className="pt-6"><div className="card p-4" role="status"><p>{deletedNotice}</p>{deletedNotice.includes("could not be confirmed") ? <a className="mt-2 inline-block underline" href="https://myaccount.google.com/connections" target="_blank" rel="noopener noreferrer">Review Google Account connections</a> : null}</div></Container> : null}
    <RequireAuth>
      <Container className="py-10 sm:py-12">
        <PageHeader
          title="Your account"
          description={
            user
              ? `Signed in as ${user.display_name || user.email}. Your research profile powers personalized recommendations and personalized outreach drafts.`
              : "Your research profile powers personalized recommendations and personalized outreach drafts."
          }
          actions={
            <Button onClick={() => router.push("/account/onboarding")}>
              Edit profile
            </Button>
          }
        />

        <UsageDashboardLink />
        {saveError ? <div className="card mt-6 p-4" role="alert"><p>{saveError}</p><Button variant="secondary" onClick={() => hydrated ? void saveProfile(profile) : retryLoad()}>Try again</Button></div> : null}
        {!hydrated || saving ? <p className="mt-3" role="status">{!hydrated ? "Loading your profile…" : "Saving changes…"}</p> : null}
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ProfileSummary profile={profile} />
            <ClearResearchProfile key={user?.user_id ?? "signed-out"} profile={profile}
              saveProfile={saveProfile} disabled={!hydrated || saving || !user}
              invalidatePreview={() => setResumeVersion(value => value + 1)} />
          </div>

          <div className="space-y-6">
            <section className="card p-5" aria-labelledby="identity-title">
              <h2 id="identity-title" className="inline-flex items-center gap-2 text-base font-semibold text-ink">
                <UserRound className="h-4 w-4 text-brand-600" aria-hidden="true" />
                Signed-in account
              </h2>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">Name</dt>
                  <dd className="truncate font-medium text-ink">{user?.display_name || "—"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">Email</dt>
                  <dd className="truncate font-medium text-ink">{user?.email || "—"}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-slate-400">
                Your saved researchers, research profile, and reviewed outreach drafts are stored with
                this account.
              </p>
            </section>

            {localImportAvailable ? <section className="card p-5" aria-labelledby="import-title">
              <h2 id="import-title" className="inline-flex items-center gap-2 text-base font-semibold text-ink">
                <HardDriveDownload className="h-4 w-4 text-brand-600" aria-hidden="true" />
                Import local data
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Move pre-sign-in local records (saved researchers, outreach status, Gmail
                connection) into this account. Available once, and only for this account.
              </p>
              <Button
                type="button"
                variant="secondary"
                className="mt-4 w-full"
                onClick={() => void runImport()}
                disabled={importing}
              >
                {importing ? "Importing…" : "Import my local data"}
              </Button>
              {importNotice ? (
                <p className="mt-3 text-sm text-ink-600" role="status">
                  {importNotice}
                </p>
              ) : null}
            </section> : null}

            <ResumeImport key={`${user?.user_id ?? "signed-out"}:${resumeVersion}`} userId={user?.user_id ?? ""}
              profile={profile} saveProfile={saveProfile} disabled={!hydrated || saving || !user} />

            <section className="card p-5" aria-labelledby="progress-title">
              <h2 id="progress-title" className="text-base font-semibold text-ink">
                Next steps
              </h2>
              <ul className="mt-3 space-y-2.5 text-sm">
                <li className="flex items-center gap-2 text-ink-600">
                  <UserRound className="h-4 w-4 text-brand-600" aria-hidden="true" />
                  Complete your research profile
                </li>
                <li className="flex items-center gap-2 text-ink-600">
                  <GraduationCap className="h-4 w-4 text-brand-600" aria-hidden="true" />
                  Explore your For You matches
                </li>
                <li className="flex items-center gap-2 text-ink-600">
                  <Send className="h-4 w-4 text-brand-600" aria-hidden="true" />
                  Draft your first outreach email
                </li>
              </ul>
              <Button className="mt-4 w-full" onClick={() => router.push("/for-you")}>
                See my matches
              </Button>
            </section>
          </div>
        </div>
        <section className="card mt-8 max-w-3xl p-5" aria-labelledby="delete-title">
          <h2 id="delete-title" className="text-base font-semibold text-ink">Delete your account</h2>
          <p className="mt-2 text-sm text-slate-600">Remove your profile, saved researchers, outreach records, active sessions and stored Gmail connection. This cannot be undone. Your Gmail messages and drafts stay in Gmail.</p>
          <p className="mt-2 text-sm text-slate-600">Older manual backups and server logs are not erased by this button. A minimal deletion receipt is kept to prevent restoring deleted account data. <a href="/privacy" className="underline">Read the retention policy.</a></p>
          {!deleteOpen ? <Button variant="secondary" className="mt-4" onClick={() => { setDeleteOpen(true); setDeleteIdentity(user?.user_id ?? null); setDeleteError(null); }}>Delete my account</Button> : (
            <div className="mt-4" role="group" aria-label="Confirm account deletion">
              <p className="break-words text-sm font-medium text-ink">Delete the account signed in as {user?.email}?</p>
              {deleteIdentity !== user?.user_id ? <p role="alert" className="mt-2 text-sm text-red-700">The signed-in account changed. Cancel and open a new confirmation before deleting.</p> : null}
              <label htmlFor="delete-confirmation" className="mt-3 block text-sm">Type DELETE to confirm</label>
              <input id="delete-confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={deleting || deleteIdentity !== user?.user_id} autoComplete="off" className="mt-2 w-full max-w-sm rounded-control border border-slate-300 p-2" />
              <div className="mt-3 flex flex-wrap gap-3">
                <Button disabled={deleting || confirmation !== "DELETE" || deleteIdentity !== user?.user_id} onClick={() => void runDelete()}>{deleting ? "Deleting account…" : "Permanently delete account"}</Button>
                <Button variant="secondary" disabled={deleting} onClick={() => { setDeleteOpen(false); setConfirmation(""); setDeleteError(null); }}>Cancel</Button>
              </div>
              {deleting ? <p role="status" className="mt-2 text-sm">Removing your data and disconnecting Gmail. Please wait.</p> : null}
              {deleteError ? <p role="alert" className="mt-3 text-sm text-red-700">{deleteError} If the connection was interrupted, refresh to check whether deletion finished. Some Gmail files may already have been removed.</p> : null}
            </div>
          )}
        </section>
      </Container>
    </RequireAuth>
    </>
  );
}

"use client";
import { useEffect, useRef, useState } from "react";
import { DEFAULT_STUDENT_PROFILE } from "@/data/studentProfile";
import { Button } from "@/components/ui/Button";
import type { StudentProfile } from "@/types";

export function ClearResearchProfile({ profile, disabled, saveProfile, invalidatePreview }: {
  profile: StudentProfile; disabled: boolean;
  saveProfile: (next: StudentProfile) => Promise<boolean>;
  invalidatePreview: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [previous, setPrevious] = useState<StudentProfile | null>(null);
  const live = useRef(true);
  const clearSnapshot = useRef<StudentProfile | null>(null);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  async function clear() {
    if (disabled || busy) return;
    const snapshot = clearSnapshot.current ?? structuredClone(profile);
    setPrevious(snapshot);
    setBusy(true); setNotice(""); invalidatePreview();
    try {
      const saved = await saveProfile(structuredClone(DEFAULT_STUDENT_PROFILE));
      if (!live.current) return;
      if (saved) {
        setPrevious(snapshot); setConfirm(false);
        setNotice("Research profile cleared. You can undo this while you stay on this page.");
      } else setNotice("Clearing could not be confirmed. Try again or refresh to check your profile.");
    } catch {
      if (live.current) setNotice("Clearing could not be confirmed. Try again or refresh to check your profile.");
    } finally { if (live.current) setBusy(false); }
  }

  async function undo() {
    if (!previous || disabled || busy) return;
    setBusy(true); setNotice(""); invalidatePreview();
    try {
      const saved = await saveProfile(previous);
      if (!live.current) return;
      if (saved) { setPrevious(null); setNotice("Your previous research profile was restored."); }
      else setNotice("Restoring could not be confirmed. Try again or refresh to check your profile.");
    } catch {
      if (live.current) setNotice("Restoring could not be confirmed. Try again or refresh to check your profile.");
    } finally { if (live.current) setBusy(false); }
  }

  return <section className="card mt-4 p-5" aria-labelledby="clear-profile-title">
    <h2 id="clear-profile-title" className="text-base font-semibold text-ink">Clear research profile</h2>
    <p className="mt-2 text-sm text-slate-600">Remove all interests, notes about your interests, skills, coursework, experience, and the selected résumé filename. Education and preferences return to their defaults. Your account, saved researchers, and outreach records stay intact.</p>
    {confirm ? <div className="mt-4" role="group" aria-label="Confirm clearing research profile">
      <p className="text-sm font-medium">Clear your entire research profile?</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="danger" disabled={disabled || busy} onClick={() => void clear()}>{busy ? "Clearing…" : "Yes, clear profile"}</Button>
        <Button variant="secondary" disabled={busy} onClick={() => setConfirm(false)}>Cancel</Button>
      </div>
    </div> : <div className="mt-4 flex flex-wrap gap-2">
      <Button variant="secondary" disabled={disabled || busy} onClick={() => { clearSnapshot.current = structuredClone(profile); setConfirm(true); }}>Clear research profile</Button>
      {previous ? <Button variant="secondary" disabled={disabled || busy} onClick={() => void undo()}>{busy ? "Restoring…" : "Undo clear"}</Button> : null}
    </div>}
    {previous && !confirm ? <p className="mt-2 text-xs text-slate-500">Undo restores the previous profile, replacing any profile edits made since clearing.</p> : null}
    {notice ? <p className="mt-3 text-sm" role="status">{notice}</p> : null}
  </section>;
}

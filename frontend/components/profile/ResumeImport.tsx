"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { apiFetch } from "@/lib/api/client";
import type { StudentProfile } from "@/types";

type Preview = { text: string; skills: string[]; coursework: string[]; experience: string[] };
const fields = ["skills", "coursework", "experience"] as const;
const lines = (value: string) => value.split("\n").map(x => x.trim()).filter(Boolean);
const merge = (old: string[], added: string[]) => Array.from(new Set([...old, ...added]));

export function ResumeImport({ userId, profile, saveProfile, disabled }: {
  userId: string; profile: StudentProfile; disabled: boolean;
  saveProfile: (profile: StudentProfile) => Promise<boolean>;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [values, setValues] = useState({ skills: "", coursework: "", experience: "" });
  const [replaceFields, setReplaceFields] = useState({ skills: false, coursework: false, experience: false });
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const [notice, setNotice] = useState("");
  const active = useRef(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => { active.current += 1; controller.current?.abort(); }, []);

  async function choose(file: File | undefined) {
    if (!file || busy || applying || disabled) return;
    const kind = file.name.split(".").pop()?.toLowerCase();
    setPreview(null); setNotice("");
    setReplaceFields({ skills: false, coursework: false, experience: false });
    if (!kind || !["pdf", "docx", "txt"].includes(kind) || !file.size || file.size > 512 * 1024) {
      setNotice("Choose a PDF, DOCX, or UTF-8 TXT file no larger than 512 KB. Older DOC files are unsupported.");
      return;
    }
    const sequence = ++active.current;
    const request = new AbortController(); controller.current = request;
    setBusy(true);
    try {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("Could not read this file."));
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.readAsDataURL(file);
      });
      if (sequence !== active.current) return;
      const result = await apiFetch<Preview>("/api/profile/resume-preview", {
        method: "POST", body: { expected_user_id: userId, kind, content },
        signal: request.signal, timeoutMs: 12000,
      });
      if (sequence !== active.current) return;
      setFileName(file.name); setPreview(result);
      setValues({ skills: result.skills.join("\n"), coursework: result.coursework.join("\n"), experience: result.experience.join("\n") });
      setNotice("Review and edit the suggestions before adding them to your profile.");
    } catch (error) {
      if (sequence === active.current) setNotice(error instanceof Error ? error.message : "Could not read this résumé.");
    } finally {
      if (sequence === active.current) setBusy(false);
    }
  }

  async function apply() {
    if (!preview || applying || disabled) return;
    if (fields.every(field => !lines(values[field]).length)) {
      setNotice("Add at least one reviewed skill, course, or experience before saving."); return;
    }
    if (fields.some(field => merge(replaceFields[field] ? [] : profile[field], lines(values[field])).length > 200)) {
      setNotice("Keep each profile field to 200 items. Remove some suggestions before saving."); return;
    }
    setApplying(true);
    const sequence = active.current;
    try {
      const saved = await saveProfile({ ...profile,
        skills: merge(replaceFields.skills ? [] : profile.skills, lines(values.skills)),
        coursework: merge(replaceFields.coursework ? [] : profile.coursework, lines(values.coursework)),
        experience: merge(replaceFields.experience ? [] : profile.experience, lines(values.experience)),
        resume: { fileName },
      });
      if (sequence === active.current) {
        setNotice(saved ? "Reviewed details added to your profile." : "Details were not saved. Please try again.");
        if (saved) setPreview(null);
      }
    } catch {
      if (sequence === active.current) setNotice("Details were not saved. Please try again.");
    } finally {
      if (sequence === active.current) setApplying(false);
    }
  }

  return <section className="card p-5" aria-labelledby="resume-title">
    <h2 id="resume-title" className="text-base font-semibold text-ink">Import résumé details (optional)</h2>
    <p className="mt-2 text-sm text-slate-600">Choose a PDF, DOCX, or TXT résumé up to 512 KB. The file is sent to this app&apos;s server for parsing, then discarded. It is not sent to AI. Only details you review and apply are saved in your profile.</p>
    <label className="mt-4 block text-sm font-medium" htmlFor="resume-upload">Choose résumé</label>
    <input id="resume-upload" type="file" accept=".pdf,.docx,.txt" disabled={disabled || busy || applying}
      className="focus-ring mt-2 block w-full min-w-0 text-sm"
      onChange={event => { void choose(event.target.files?.[0]); event.target.value = ""; }} />
    {busy ? <p role="status" className="mt-3 text-sm">Reading your résumé…</p> : null}
    {notice ? <p role="status" className="mt-3 text-sm">{notice}</p> : null}
    {preview ? <div className="mt-4 space-y-4">
      <p className="break-words text-sm font-medium">Review {fileName}</p>
      <details><summary className="cursor-pointer text-sm">View extracted text</summary>
        <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-xs">{preview.text}</pre>
      </details>
      <p className="text-xs text-slate-500">One item per line. Clear any field you don&apos;t want to import. Existing profile details are kept unless you choose Replace existing for that field.</p>
      {fields.map(field => <div key={field}><label className="block text-sm capitalize">{field}
        <textarea className="focus-ring mt-1 w-full rounded-control border border-border p-2" rows={3}
          maxLength={8000} disabled={applying} value={values[field]}
          onChange={event => setValues(current => ({ ...current, [field]: event.target.value }))} />
      </label>
        <label className="mt-2 flex items-start gap-2 text-sm">
          <input type="checkbox" checked={replaceFields[field]} disabled={applying}
            className="mt-1" onChange={event => setReplaceFields(current => ({ ...current, [field]: event.target.checked }))} />
          Replace existing {field} with these reviewed details
        </label>
      </div>)}
      <div className="flex flex-wrap gap-2">
        <Button disabled={disabled || applying} onClick={() => void apply()}>{applying ? "Saving…" : "Add reviewed details"}</Button>
        <Button variant="secondary" disabled={applying} onClick={() => { setPreview(null); setNotice("Preview discarded. Your profile was not changed."); }}>Discard preview</Button>
      </div>
    </div> : null}
  </section>;
}

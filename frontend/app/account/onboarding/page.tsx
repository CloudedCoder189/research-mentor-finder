"use client";

import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ResumeImport } from "@/components/profile/ResumeImport";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { Input, InlineNotice, Textarea } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  COURSEWORK_OPTIONS,
  INTEREST_OPTIONS,
  SKILL_OPTIONS,
} from "@/data/options";
import { getSearchOptions } from "@/lib/api/researchers";
import type { EducationLevel } from "@/types";
import { useStudentProfile } from "@/lib/useStudentProfile";

const STEPS = ["Interests", "Skills", "Experience", "Coursework", "Preferences"] as const;

const STEP_STORAGE_KEY = "rmf:onboarding:step";

function readSavedStep(): number {
  if (typeof window === "undefined") return 0;
  try {
    const raw = window.localStorage.getItem(STEP_STORAGE_KEY);
    const parsed = Number(raw);
    return Number.isInteger(parsed) && parsed >= 0 && parsed < STEPS.length ? parsed : 0;
  } catch {
    return 0;
  }
}

function ChipField({
  label,
  hint,
  items,
  options,
  onToggle,
  allowCustom = true,
}: {
  label: string;
  hint?: string;
  items: string[];
  options: string[];
  onToggle: (value: string) => void;
  allowCustom?: boolean;
}) {
  const [custom, setCustom] = useState("");
  const addCustom = () => {
    const value = custom.trim();
    if (value && !items.includes(value)) onToggle(value);
    setCustom("");
  };
  return (
    <div>
      <h3 className="text-base font-semibold text-ink">{label}</h3>
      {hint ? <p className="mt-1 text-sm text-slate-500">{hint}</p> : null}
      <ul className="mt-3 flex flex-wrap gap-2" aria-label={label}>
        {Array.from(new Set([...options, ...items])).map((option) => {
          const selected = items.includes(option);
          return (
            <li key={option}>
              <button
                type="button"
                onClick={() => onToggle(option)}
                aria-pressed={selected}
                className={
                  "focus-ring rounded-pill border px-3 py-1.5 text-sm font-medium transition-colors " +
                  (selected
                    ? "border-brand-200 bg-brand-100 text-brand-700"
                    : "border-border bg-surface text-ink-600 hover:bg-brand-50")
                }
              >
                {option}
              </button>
            </li>
          );
        })}
      </ul>
      {allowCustom ? (
        <div className="mt-3 grid max-w-sm grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
          <Input
            id={`${label}-custom`}
            aria-label={`Add custom item: ${label}`}
            placeholder="Add your own…"
            className="h-11"
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addCustom();
              }
            }}
          />
          <Button type="button" variant="secondary" className="whitespace-nowrap" onClick={addCustom}>
            Add
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export default function OnboardingPage() {
  const { profile, saveProfile, hydrated, saving, saveError, retryLoad } = useStudentProfile();
  const router = useRouter();
  const [step, setStep] = useState(readSavedStep);
  const [done, setDone] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [attemptedInterestGuard, setAttemptedInterestGuard] = useState(false);
  const [locationOptions, setLocationOptions] = useState<string[]>([]);
  const [locationError, setLocationError] = useState(false);
  const [locationRetry, setLocationRetry] = useState(0);
  const [experienceInput, setExperienceInput] = useState("");
  const { user } = useAuth();

  useEffect(() => {
    try {
      window.localStorage.setItem(STEP_STORAGE_KEY, String(step));
    } catch {
      /* storage unavailable */
    }
  }, [step]);

  useEffect(() => {
    let current = true;
    void getSearchOptions().then(options => { if (current) { setLocationOptions(options.states); setLocationError(false); } }).catch(() => { if (current) setLocationError(true); });
    return () => { current = false; };
  }, [locationRetry]);

  const toggle = (key: "interests" | "skills" | "coursework", value: string) => {
    const list = profile[key];
    const next = list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
    saveProfile({ ...profile, [key]: next });
  };

  const canContinue = step === 0 ? profile.interests.length > 0 : true;

  /*
   * Interests are the only required step, so every route forward has to respect
   * that rule: the progress nav must not jump past an unmet requirement, the
   * Skip link must not exist on the required step, and saving must refuse an
   * incomplete profile rather than persist one that contradicts the message
   * shown on the step itself.
   */
  const gotoStep = (index: number) => {
    // Leaving Interests (forward from step 0, or a direct jump) requires them.
    if (step === 0 && index > 0 && profile.interests.length === 0) {
      setAttemptedInterestGuard(true);
      return;
    }
    setAttemptedInterestGuard(false);
    setStep(index);
  };

  const saveAndFinish = async () => {
    if (profile.interests.length === 0) {
      setAttemptedInterestGuard(true);
      setStep(0);
      return;
    }
    setFinishing(true);
    const saved = await saveProfile({ ...profile, completed: true });
    setFinishing(false);
    if (!saved) return;
    try {
      window.localStorage.removeItem(STEP_STORAGE_KEY);
    } catch {
      /* storage unavailable */
    }
    setDone(true);
    router.push("/for-you");
  };

  const progress = ((step + 1) / STEPS.length) * 100;

  return (
    <RequireAuth>
      <Container className="py-10 sm:py-12">
      <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Build your research profile"
        description="A little about you, a better match. Only interests are required — everything else can be skipped or added later."
      />

        {saveError ? (
          <div className="card mt-6 p-4" role="alert">
            <p>{saveError}</p>
            <Button variant="secondary" className="mt-3" onClick={() => hydrated ? void saveProfile(profile) : retryLoad()}>
              Try again
            </Button>
          </div>
        ) : null}
        <p className="mt-3 text-sm text-slate-500" role="status">
          {!hydrated ? "Loading your profile…" : saving ? "Saving changes…" : saveError ? "Changes not saved" : "Profile ready"}
        </p>
        <fieldset disabled={!hydrated || finishing}>
        <nav aria-label="Progress" className="mt-8">
          <ol className="flex flex-wrap gap-x-2 gap-y-1 text-sm">
            {STEPS.map((label, index) => (
              <li key={label} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => gotoStep(index)}
                  className={
                    "focus-ring rounded-pill px-2.5 py-1 text-xs font-semibold " +
                    (index === step
                      ? "bg-brand-100 text-brand-700"
                      : index < step
                        ? "text-brand-700"
                        : "text-slate-400")
                  }
                >
                  {index < step ? <CheckCircle2 className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" /> : null}
                  {label}
                </button>
                {index < STEPS.length - 1 ? <span className="text-slate-300">·</span> : null}
              </li>
            ))}
          </ol>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="Research profile progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
        </nav>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
        {done ? (
          <section className="card mt-8 p-8 text-center" aria-live="polite">
            <CheckCircle2 className="mx-auto h-12 w-12 text-accent-600" aria-hidden="true" />
            <h2 className="mt-4 text-xl font-bold text-ink">Profile saved</h2>
            <p className="mt-2 text-sm text-slate-500">
              Your recommendations will be personalized from these answers.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button variant="secondary" onClick={() => router.push("/for-you")}>
                See my matches
              </Button>
            </div>
          </section>
        ) : (
          <div className="card mt-8 p-6 sm:p-8">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Step {step + 1} of {STEPS.length}
            </p>

            {step === 0 ? (
              <div className="mt-4 space-y-4">
                <div>
                  <h3 className="text-xl font-bold tracking-tight text-ink-950">
                    What are you curious about?
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    You can start with just your interests and improve your profile later.
                  </p>
                </div>
                <div>
                  <label htmlFor="education-level" className="field-label">Education level (optional)</label>
                  <select id="education-level" className="focus-ring h-10 w-full rounded-control border border-border bg-surface px-3 text-sm text-ink" value={profile.education_level} onChange={event => saveProfile({ ...profile, education_level: event.target.value as EducationLevel })}>
                    <option value="unspecified">Not specified</option><option value="high_school">High school</option><option value="college">College</option><option value="university">University</option><option value="graduate">Graduate school</option>
                  </select>
                  <p className="mt-1 text-xs text-slate-500">Used for draft wording. Choose your actual level; we do not infer it from your résumé.</p>
                </div>
                <ChipField
                  label="Which research areas interest you?"
                  hint="Pick at least one — this is what recommendations will be matched on."
                  items={profile.interests}
                  options={INTEREST_OPTIONS}
                  onToggle={(value) => toggle("interests", value)}
                />
                <Textarea
                  id="interest-description"
                  label="Tell us more (optional)"
                  hint="A sentence or two about what you want to work on. This sharpens recommendations beyond the chips."
                  placeholder="For example: I want to build assistive technology that makes health information easier to understand."
                  value={profile.interestText}
                  onChange={(event) =>
                    saveProfile({ ...profile, interestText: event.target.value })
                  }
                  rows={3}
                />
                {profile.interests.length === 0 || attemptedInterestGuard ? (
                  <InlineNotice tone="amber">Please select at least one interest to continue.</InlineNotice>
                ) : null}
              </div>
            ) : null}

            {step === 1 ? (
              <div className="mt-4 space-y-4">
                <ChipField
                  label="What are you good at?"
                  hint="Skills help us explain why a researcher might be a practical fit. Optional."
                  items={profile.skills}
                  options={SKILL_OPTIONS}
                  onToggle={(value) => toggle("skills", value)}
                />
              </div>
            ) : null}

            {step === 2 ? (
              <div className="mt-4 space-y-4">
                <h3 className="text-base font-semibold text-ink">Experience</h3>
                <p className="text-sm text-slate-500">
                  Projects, classes you led, competitions, hackathons — anything relevant. Optional.
                </p>
                <div className="grid max-w-sm grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
                  <Input
                    id="experience-input"
                    aria-label="Add an experience"
                    placeholder="Add an experience…"
                    className="h-11"
                    value={experienceInput}
                    onChange={(event) => setExperienceInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        const value = experienceInput.trim();
                        if (value) saveProfile({ ...profile, experience: [...profile.experience, value] });
                        setExperienceInput("");
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    className="whitespace-nowrap"
                    onClick={() => {
                      const value = experienceInput.trim();
                      if (value) saveProfile({ ...profile, experience: [...profile.experience, value] });
                      setExperienceInput("");
                    }}
                  >
                    Add
                  </Button>
                </div>
                {profile.experience.length > 0 ? (
                  <ul className="space-y-2">
                    {profile.experience.map((item) => (
                      <li key={item} className="flex items-start justify-between gap-3 rounded-control border border-border bg-slate-50 px-3 py-2 text-sm text-ink-600">
                        <span>{item}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${item}`}
                          onClick={() =>
                            saveProfile({ ...profile, experience: profile.experience.filter((e) => e !== item) })
                          }
                          className="focus-ring rounded-control px-1 text-slate-400 hover:text-rose-600"
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {step === 3 ? (
              <div className="mt-4 space-y-4">
                <ChipField
                  label="Which courses have you taken?"
                  hint="Optional — used to explain the foundation for your interests."
                  items={profile.coursework}
                  options={COURSEWORK_OPTIONS}
                  onToggle={(value) => toggle("coursework", value)}
                />
              </div>
            ) : null}

            {step === 4 ? (
              <div className="mt-4 space-y-6">
                <ChipField
                  label="Preferred locations"
                  items={profile.preferences.locations}
                  options={Array.from(new Set([...locationOptions, ...profile.preferences.locations]))}
                  onToggle={(value) => {
                    const locations = profile.preferences.locations.includes(value)
                      ? profile.preferences.locations.filter((item) => item !== value)
                      : [...profile.preferences.locations, value];
                    saveProfile({ ...profile, preferences: { ...profile.preferences, locations } });
                  }}
                  allowCustom={false}
                />
                <p className="text-sm text-slate-500">Leave locations empty to consider all regions. Locations influence matching; they do not confirm on-site or remote availability.</p>
                {locationError ? <div role="alert"><p>Locations could not be loaded. Your saved locations are retained.</p><Button type="button" variant="secondary" onClick={() => setLocationRetry(value => value + 1)}>Retry locations</Button></div> : null}

                <ResumeImport key={user?.user_id ?? "signed-out"} userId={user?.user_id ?? ""}
                  profile={profile} saveProfile={saveProfile} disabled={!hydrated || saving || !user} />
              </div>
            ) : null}

            <div className="mt-6 border-t border-border pt-5">
              <Button type="button" onClick={saveAndFinish} disabled={!hydrated || finishing || !profile.interests.length}>{finishing ? "Saving profile…" : "See my matches"}</Button>
              <p className="mt-2 text-sm text-slate-500">Ready with just your interests. Add optional background below or return to edit it later.</p>
            </div>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <Button
                type="button"
                variant="secondary"
                onClick={() => gotoStep(Math.max(0, step - 1))}
                disabled={step === 0}
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Back
              </Button>
              {step < STEPS.length - 1 ? (
                <Button type="button" onClick={() => gotoStep(step + 1)} disabled={!canContinue}>
                  Add optional background
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              ) : (
                <Button type="button" onClick={saveAndFinish} disabled={!hydrated || finishing}>
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  {finishing ? "Saving profile…" : "Save profile"}
                </Button>
              )}
            </div>

            {/* Interests are required, so the required step offers no Skip link. */}
            {step < STEPS.length - 1 && step !== 0 ? (
              <div className="mt-4 text-right">
                <button
                  type="button"
                  onClick={() => gotoStep(step + 1)}
                  className="focus-ring rounded-control px-1 py-0.5 text-sm font-medium text-slate-400 hover:text-slate-600"
                >
                  Skip this step for now
                </button>
              </div>
            ) : null}
          </div>
        )}
          </div>

          <aside className="lg:col-span-5">
            <div className="space-y-4 lg:sticky lg:top-24">
              <section className="panel-aqua p-5">
                <h3 className="text-sm font-semibold text-accent-700">
                  A little about you. Better matches.
                </h3>
                <p className="mt-2 text-sm text-ink-600">
                  Recommendations are ranked against your real interests, not generic filters.
                </p>
              </section>
              <section className="panel-aqua p-5">
                <h3 className="text-sm font-semibold text-accent-700">
                  No research experience needed.
                </h3>
                <p className="mt-2 text-sm text-ink-600">
                  Interests alone are enough to start. Skills and projects sharpen the fit.
                </p>
              </section>
              <section className="panel-aqua p-5">
                <h3 className="text-sm font-semibold text-accent-700">
                  Have a résumé? Optional.
                </h3>
                <p className="mt-2 text-sm text-ink-600">
                  You can attach one anytime from your profile page.
                </p>
              </section>
            </div>
          </aside>
        </div>

        </fieldset>
        <p className="mt-6 text-center text-xs text-slate-400">
          Only interests are required. You can skip the other steps.
        </p>
      </div>
    </Container>
    </RequireAuth>
  );
}

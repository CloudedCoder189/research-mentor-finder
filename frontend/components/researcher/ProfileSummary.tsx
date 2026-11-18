import { FileText, PencilLine, Sparkles } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import type { StudentProfile } from "@/types";

function ChipGroup({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h4>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <li key={item} className="chip-light max-w-full">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ProfileSummary({
  profile,
  compact = false,
  className,
}: {
  profile: StudentProfile;
  compact?: boolean;
  className?: string;
}) {
  return (
    <Card className={cn("min-w-0 p-5 [overflow-wrap:anywhere]", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="inline-flex items-center gap-2 text-base font-semibold text-ink">
          <UserIcon />
          Your research profile
        </h3>
        {!compact ? (
          <Link
            href="/account/onboarding"
            className="focus-ring inline-flex items-center gap-1 rounded-control px-2 py-1 text-sm font-medium text-brand-700 hover:bg-brand-50"
          >
            <PencilLine className="h-4 w-4" aria-hidden="true" />
            Edit
          </Link>
        ) : null}
      </div>

      <div className={cn("mt-4", compact ? "space-y-3" : "space-y-4")}>
        <p className="text-sm text-ink-600">Education: {({ unspecified: "Not specified", high_school: "High school", college: "College", university: "University", graduate: "Graduate school" })[profile.education_level] ?? "Not specified"}</p>
        <ChipGroup title="Interests" items={profile.interests} />
        <ChipGroup title="Skills" items={profile.skills} />
        {!compact ? <ChipGroup title="Coursework" items={profile.coursework} /> : null}
        {!compact && profile.experience.length > 0 ? (
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Experience
            </h4>
            <ul className="mt-2 space-y-1.5 text-sm text-ink-600">
              {profile.experience.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-300" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="text-sm text-ink-600">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Preferences
          </h4>
          <p className="mt-2">
            Region: {profile.preferences.locations.join(", ") || "No preference"}
          </p>
          <p className="mt-2 text-xs text-slate-500">Region can affect ranking. Confirm mentoring and remote availability with the researcher.</p>
        </div>
      </div>

      {!compact ? (
        <div className="hairline mt-5 pt-4">
          <h4 className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            Résumé
          </h4>
          <p className="mt-2 text-sm text-slate-500">
            {profile.resume.fileName ? (
              <>
                Last selected file: <span className="font-medium text-ink">{profile.resume.fileName}</span>
              </>
            ) : (
              "Import reviewed résumé details from your Account page."
            )}
          </p>
        </div>
      ) : null}
    </Card>
  );
}

function UserIcon() {
  return <Sparkles className="h-4 w-4 text-brand-600" aria-hidden="true" />;
}

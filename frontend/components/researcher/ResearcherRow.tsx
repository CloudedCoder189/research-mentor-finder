import { Building2, ExternalLink } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { MatchBadge } from "@/components/researcher/MatchBadge";
import { OutreachStatusBadge } from "@/components/researcher/OutreachStatusBadge";
import { ResearchTopicTags } from "@/components/researcher/ResearchTopicTags";
import { SaveButton } from "@/components/researcher/SaveButton";
import { VerifiedBadge } from "@/components/researcher/VerifiedBadge";
import { LinkButton } from "@/components/ui/Button";
import { initials } from "@/lib/format";
import type { OutreachStatus, Researcher, ResearcherMatch } from "@/types";

export function ResearcherRow({
  researcher,
  match,
  outreachStatus,
  showSave = true,
  extraActions,
  hideProfileLink = false,
  profileHref,
}: {
  researcher: Researcher;
  match?: ResearcherMatch;
  outreachStatus?: OutreachStatus;
  showSave?: boolean;
  extraActions?: ReactNode;
  hideProfileLink?: boolean;
  profileHref?: string;
}) {
  const topicLead = match?.reasons[0];

  return (
    <article className="card p-4 sm:p-5" aria-label={researcher.name}>
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-stretch lg:gap-5">
        <div className="lg:col-span-5">
          <div className="flex min-h-full flex-col gap-3">
            <div className="flex items-start gap-3">
              <div
                aria-hidden="true"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-control bg-slate-100 text-sm font-semibold text-ink-500"
              >
                {initials(researcher.name)}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Link
                    href={profileHref ?? `/researchers/${researcher.id}`}
                    className="focus-ring text-base font-semibold text-ink-900 hover:text-brand-700 hover:underline"
                  >
                    {researcher.name}
                  </Link>
                  <VerifiedBadge status={researcher.verificationStatus} />
                </div>
                <p className="mt-1 text-sm text-slate-500">
                  {researcher.title} · {researcher.department}
                </p>
                <p className="mt-0.5 inline-flex items-center gap-1 text-sm text-slate-500">
                  <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {researcher.university} — {researcher.city}, {researcher.state}
                </p>
              </div>
            </div>
            <ResearchTopicTags topics={researcher.topics} max={3} />
          </div>
        </div>

        <div className="lg:col-span-4">
          <div className="panel-aqua flex h-full flex-col gap-2 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent-700">
              Research fit
            </p>
            {topicLead ? (
              <p className="text-sm leading-relaxed text-ink-700">{topicLead}</p>
            ) : (
              <p className="text-sm leading-relaxed text-ink-700">
                {researcher.topics[0]
                  ? `This researcher’s published research areas include ${researcher.topics[0].toLowerCase()} and related topics.`
                  : "Open the profile and its original source to evaluate research fit."}
              </p>
            )}
          </div>
        </div>

        <div className="lg:col-span-3">
          <div className="flex h-full flex-wrap items-center justify-start gap-2 lg:flex-col lg:flex-nowrap lg:items-start">
            {match ? <MatchBadge label={match.label} /> : null}
            {outreachStatus ? <OutreachStatusBadge status={outreachStatus} /> : null}
            <div className="flex flex-wrap items-center gap-2 lg:w-full">
              {extraActions}
              {showSave ? <SaveButton researcherId={researcher.id} /> : null}
              {!hideProfileLink ? (
                <LinkButton
                  href={profileHref ?? `/researchers/${researcher.id}`}
                  variant="secondary"
                  size="sm"
                  aria-label={`View profile of ${researcher.name}`}
                >
                  View profile
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </LinkButton>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

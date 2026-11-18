"use client";

import {
  ArrowLeft,
  BookOpen,
  FileText,
  Globe,
  Link2,
  Mail,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { OutreachCard } from "@/components/researcher/profile/OutreachCard";
import { ProfileResearchGuide } from "@/components/learning/ProfileResearchGuide";
import { MatchBadge } from "@/components/researcher/MatchBadge";
import { SaveButton } from "@/components/researcher/SaveButton";
import { ResearchTopicTags } from "@/components/researcher/ResearchTopicTags";
import { VerifiedBadge } from "@/components/researcher/VerifiedBadge";
import { WhyMatchPanel } from "@/components/researcher/WhyMatchPanel";
import { Button, LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api/client";
import { toProfileInput, toProfileResearcher, toRecommendationResult } from "@/lib/api/map";
import { explainMatch } from "@/lib/api/recommendations";
import { getResearcherProfile } from "@/lib/api/researchers";
import type { ResearcherProfileDto } from "@/lib/api/types";
import { hasResearchInterests } from "@/data/studentProfile";
import { useStudentProfile } from "@/lib/useStudentProfile";
import { WEBSITE_META } from "@/lib/meta";
import type { Researcher, ResearcherMatch } from "@/types";

type Status =
  | { kind: "loading" }
  | { kind: "error"; error: ApiError }
  | { kind: "ready"; profile: ResearcherProfileDto; researcher: Researcher };

type ExplainState =
  | { kind: "none" }
  | { kind: "loading" }
  | { kind: "ready"; match: ResearcherMatch }
  | { kind: "fallback" };

const NOT_AVAILABLE = "Not publicly available";

function clean(value: string): string {
  const cleaned = value.trim();
  return cleaned && cleaned !== NOT_AVAILABLE ? cleaned : "";
}

function ResearchConnection({ researcher }: { researcher: Researcher }) {
  const topics = researcher.topics;
  const summary = clean(researcher.researchOverview);
  const interests = clean(researcher.researchInterests);
  const headline = topics.length
    ? `This researcher’s published research areas are ${topics.slice(0, 5).join(", ")}.`
    : summary || interests || "Research details are unavailable. Review the original source before evaluating fit.";

  return (
    <section className="panel-aqua p-5 sm:p-6" aria-labelledby="research-fit-title">
      <h2
        id="research-fit-title"
        className="inline-flex items-center gap-2 text-base font-semibold text-accent-700"
      >
        <BookOpen className="h-4 w-4" aria-hidden="true" />
        Research fit
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-ink-700">
        {headline}{" "}
        {topics.length || summary || interests ? <span className="text-slate-500">
          Talk to your advisor about how these areas fit your goals.
        </span> : null}
      </p>
      {topics.length ? (
        <div className="mt-3">
          <ResearchTopicTags topics={topics} />
        </div>
      ) : null}
    </section>
  );
}

function ProfileHeader({ researcher }: { researcher: Researcher }) {
  return (
    <section className="card p-6 sm:p-8" aria-label={researcher.name}>
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
        {researcher.university}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-ink-950 sm:text-3xl">
          {researcher.name}
        </h1>
        <span className="sr-only">Verified status:</span>
        <VerifiedBadge status={researcher.verificationStatus} />
      </div>
      <p className="mt-2 text-base text-ink-700">{researcher.title}</p>
      <p className="mt-1 text-sm text-slate-500">
        {researcher.department} · {researcher.university} · {researcher.city},{" "}
        {researcher.state}
      </p>
      <div className="mt-4">
        <ResearchTopicTags topics={researcher.topics} />
      </div>
    </section>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading profile" aria-busy="true">
      <div className="card animate-pulse p-8">
        <div className="flex items-start gap-4">
          <div className="h-14 w-14 rounded-control bg-slate-200" />
          <div className="flex-1 space-y-3">
            <div className="h-6 w-1/2 rounded bg-slate-200" />
            <div className="h-3 w-2/3 rounded bg-slate-100" />
            <div className="h-3 w-1/3 rounded bg-slate-100" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="card animate-pulse p-6">
            <div className="h-4 w-1/4 rounded bg-slate-200" />
            <div className="mt-4 h-3 w-full rounded bg-slate-100" />
            <div className="mt-2 h-3 w-5/6 rounded bg-slate-100" />
          </div>
        </div>
        <div className="card animate-pulse p-6">
          <div className="h-4 w-1/2 rounded bg-slate-200" />
          <div className="mt-4 h-3 w-full rounded bg-slate-100" />
        </div>
      </div>
    </div>
  );
}

export function ProfilePageView({ id, discoverHref = "/discover" }: { id: string; discoverHref?: string }) {
  const { profile: studentProfile, hydrated } = useStudentProfile();
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  const [explain, setExplain] = useState<ExplainState>({ kind: "none" });

  useEffect(() => {
    let cancelled = false;
    setStatus({ kind: "loading" });

    getResearcherProfile(id)
      .then((profile) => {
        if (!cancelled) {
          setStatus({ kind: "ready", profile, researcher: toProfileResearcher(profile) });
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          const error =
            caught instanceof ApiError ? caught : new ApiError("unavailable", "Unexpected error");
          setStatus({ kind: "error", error });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id, retry]);

  useEffect(() => {
    if (!hydrated || !hasResearchInterests(studentProfile)) {
      setExplain({ kind: "none" });
      return;
    }
    let cancelled = false;
    setExplain({ kind: "loading" });

    explainMatch(toProfileInput(studentProfile), id)
      .then((response) => {
        if (cancelled) return;
        if (response.results.length === 0) {
          setExplain({ kind: "fallback" });
          return;
        }
        const { match } = toRecommendationResult(response.results[0]);
        setExplain({ kind: "ready", match });
      })
      .catch(() => {
        if (!cancelled) setExplain({ kind: "fallback" });
      });

    return () => {
      cancelled = true;
    };
  }, [id, hydrated, studentProfile]);

  if (status.kind === "loading") {
    return (
      <Container className="py-10 sm:py-12">
        <Link
          href={discoverHref}
          className="focus-ring inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Discover
        </Link>
        <div className="mt-4">
          <LoadingSkeleton />
        </div>
      </Container>
    );
  }

  if (status.kind === "error") {
    return (
      <Container className="py-10 sm:py-12">
        {status.error.kind === "not-found" || status.error.kind === "invalid" ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" aria-hidden="true" />}
            title="This professor is not in the live directory yet"
            description="The record may be part of a future data refresh, or the link may be outdated. Browse the live directory to find current researchers."
            action={
              <LinkButton href={discoverHref}>
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Back to Discover
              </LinkButton>
            }
          />
        ) : (
          <EmptyState
            icon={<ShieldCheck className="h-6 w-6" aria-hidden="true" />}
            title="We couldn’t load this profile"
            description={status.error.message}
            action={
              <Button
                variant="secondary"
                onClick={() => { setStatus({ kind: "loading" }); setRetry((value) => value + 1); }}
              >
                Try again
              </Button>
            }
          />
        )}
      </Container>
    );
  }

  const { profile, researcher } = status;
  const websiteMeta = WEBSITE_META[researcher.websiteStatus];
  const verifier = clean(profile.verification_issues);
  const lastChecked = clean(profile.last_checked_at);
  const verifiedAt = clean(profile.verified_at);
  const signals = clean(profile.opportunity_signals);

  return (
    <Container className="py-10 sm:py-12">
      <Link
        href={discoverHref}
        className="focus-ring inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Discover
      </Link>

      <ProfileHeader researcher={researcher} />
      <p className="mt-4 text-sm text-slate-500">
        Something incorrect?{" "}
        <a className="focus-ring rounded-control font-medium text-brand-700 underline" href={`mailto:researchmentorfinder@gmail.com?subject=${encodeURIComponent(`Researcher correction: ${researcher.name} (#${researcher.id})`)}&body=${encodeURIComponent(`Researcher: ${researcher.name}\nUniversity: ${researcher.university}\nProfile: https://researchmentorfinder.org/researchers/${researcher.id}\n\nWhat seems incorrect?\n\nCorrect information and official source (if available):\n`)}`}>
          Report an issue with this profile
        </a>. Opens an email draft for you to review and send.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {explain.kind === "ready" ? (
            <div className="panel-aqua p-5 sm:p-6" aria-label="Why you match">
              <WhyMatchPanel match={explain.match} researcher={researcher} />
            </div>
          ) : explain.kind === "loading" ? (
            <div
              className="card animate-pulse p-5 sm:p-6"
              aria-busy="true"
              aria-label="Personalizing your match"
            >
              <div className="h-4 w-1/3 rounded bg-slate-200" />
              <div className="mt-3 h-3 w-full rounded bg-slate-100" />
              <div className="mt-2 h-3 w-5/6 rounded bg-slate-100" />
            </div>
          ) : (
            <ResearchConnection researcher={researcher} />
          )}

          {clean(researcher.researchOverview) ? (
            <section className="card p-5 sm:p-6" aria-labelledby="overview-title">
              <h2
                id="overview-title"
                className="inline-flex items-center gap-2 text-base font-semibold text-ink"
              >
                <FileText className="h-4 w-4 text-brand-600" aria-hidden="true" />
                Research overview
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-ink-600">
                {researcher.researchOverview}
              </p>
            </section>
          ) : null}

          {clean(researcher.researchInterests) ? (
            <section className="card p-5 sm:p-6" aria-labelledby="interests-title">
              <h2 id="interests-title" className="text-base font-semibold text-ink">
                Research interests
              </h2>
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-600">
                {researcher.researchInterests}
              </p>
            </section>
          ) : null}

          <ProfileResearchGuide researcher={researcher} />
          <details className="card p-5 sm:p-6" aria-label="Source details">
            <summary className="cursor-pointer list-none text-base font-semibold text-ink">
              Source details
            </summary>
            <p className="mt-3 text-sm text-slate-500">Record checks concern the academic profile and its sources. They do not confirm that the researcher is accepting students, or that you meet eligibility requirements. Check the original sources before reaching out.</p>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Source type</dt>
                <dd className="font-medium text-ink">{researcher.source || NOT_AVAILABLE}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Collected from</dt>
                <dd className="truncate font-medium text-ink">
                  {researcher.sourceUrl ? (
                    <a
                      href={researcher.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {researcher.sourceUrl}
                    </a>
                  ) : (
                    NOT_AVAILABLE
                  )}
                </dd>
              </div>
              {lastChecked ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-slate-500">Last data check</dt>
                  <dd className="font-medium text-ink">{lastChecked}</dd>
                </div>
              ) : null}
              {verifiedAt ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-slate-500">Verified on</dt>
                  <dd className="font-medium text-ink">{verifiedAt}</dd>
                </div>
              ) : null}
              {signals ? (
                <div className="flex flex-col gap-1">
                  <dt className="text-slate-500">Opportunity signals</dt>
                  <dd className="text-ink-600">{signals}</dd>
                </div>
              ) : null}
              {verifier ? (
                <div className="flex flex-col gap-1">
                  <dt className="text-slate-500">Verification note</dt>
                  <dd className="text-ink-600">{verifier}</dd>
                </div>
              ) : null}
            </dl>
          </details>
        </div>

        <aside className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            {explain.kind === "ready" ? <MatchBadge label={explain.match.label} /> : null}
            <SaveButton researcherId={researcher.id} />
          </div>

          <section className="card p-5" aria-labelledby="start-title">
            <h2 id="start-title" className="text-base font-semibold text-ink-950">
              Start a conversation
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Create a personalized draft using your profile and this researcher’s work.
            </p>
            <div className="mt-4">
              <LinkButton href={`/outreach/compose/${researcher.id}`} className="w-full">
                <Mail className="h-4 w-4" aria-hidden="true" />
                Draft outreach email
              </LinkButton>
            </div>
            <p className="mt-3 text-xs text-slate-400">
              You review the draft before sending. Nothing is sent automatically.
            </p>
          </section>

          <OutreachCard researcherId={researcher.id} />

          <section className="card p-5" aria-labelledby="contact-title">
            <h2
              id="contact-title"
              className="inline-flex items-center gap-2 text-base font-semibold text-ink"
            >
              <Mail className="h-4 w-4 text-brand-600" aria-hidden="true" />
              Academic contact
            </h2>
            <p className="mt-3">
              {researcher.email ? (
                <a
                  href={`mailto:${researcher.email}`}
                  className="focus-ring rounded-control text-sm font-medium text-brand-700 hover:underline"
                >
                  {researcher.email}
                </a>
              ) : (
                <span className="text-sm text-slate-500">{NOT_AVAILABLE}</span>
              )}
            </p>
            <p className="mt-2 text-xs text-slate-400">
              Address as published on the official roster.
            </p>
          </section>

          <section className="card p-5" aria-labelledby="links-title">
            <h2
              id="links-title"
              className="inline-flex items-center gap-2 text-base font-semibold text-ink"
            >
              <Link2 className="h-4 w-4 text-brand-600" aria-hidden="true" />
              Official profile &amp; lab links
            </h2>
            <ul className="mt-3 space-y-2.5 text-sm">
              {researcher.profileUrl ? (
                <li className="flex items-start gap-2">
                  <Globe className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
                  <a
                    href={researcher.profileUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="focus-ring rounded-control font-medium text-brand-700 hover:underline"
                  >
                    Official faculty profile
                  </a>
                </li>
              ) : (
                <li className="flex items-start gap-2 text-slate-500">
                  <Globe className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
                  No verified faculty profile link available
                </li>
              )}
              {researcher.websiteUrl ? (
                <li className="flex items-start justify-between gap-3">
                  <a
                    href={researcher.websiteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="focus-ring inline-flex items-center gap-2 rounded-control font-medium text-brand-700 hover:underline"
                  >
                    <ShieldCheck className="h-4 w-4 text-accent-600" aria-hidden="true" />
                    Lab / personal website
                  </a>
                  <span
                    className={`rounded-pill border px-2 py-0.5 text-xs font-medium ${websiteMeta.pill}`}
                  >
                    {websiteMeta.label}
                  </span>
                </li>
              ) : null}
            </ul>
          </section>
        </aside>
      </div>
    </Container>
  );
}

"use client";

import { SearchX, Sparkles, WifiOff } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ProfileSummary } from "@/components/researcher/ProfileSummary";
import { ResearcherRow } from "@/components/researcher/ResearcherRow";
import { WhyMatchPanel } from "@/components/researcher/WhyMatchPanel";
import type { FilterBarOptions, FilterValues } from "@/components/search/FilterBar";
import { EMPTY_FILTERS, FilterBar } from "@/components/search/FilterBar";
import { Button, LinkButton } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorHelp } from "@/components/ui/ErrorHelp";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError } from "@/lib/api/client";
import { toProfileInput, toRecommendationResult } from "@/lib/api/map";
import { getRecommendations } from "@/lib/api/recommendations";
import { getSearchOptions } from "@/lib/api/researchers";
import type { OptionsDto, RecommendationFiltersDto } from "@/lib/api/types";
import { hasResearchInterests } from "@/data/studentProfile";
import { useStudentProfile } from "@/lib/useStudentProfile";
import type { Researcher, ResearcherMatch } from "@/types";

const PAGE_SIZE = 10;

function optionLists(options?: OptionsDto): Partial<FilterBarOptions> {
  if (!options) return {};
  return {
    universities: options.universities,
    fields: options.fields,
    states: options.states,
    verificationStatuses: options.verification_statuses,
    opportunitySignals: options.opportunity_signals,
  };
}

function filtersToDto(filters: FilterValues): RecommendationFiltersDto {
  const dto: RecommendationFiltersDto = {};
  if (filters.university !== EMPTY_FILTERS.university) dto.university = filters.university;
  if (filters.field !== EMPTY_FILTERS.field) dto.field = filters.field;
  if (filters.state !== EMPTY_FILTERS.state) dto.state = filters.state;
  if (filters.verification !== EMPTY_FILTERS.verification) dto.verification = filters.verification;
  if (filters.opportunity !== EMPTY_FILTERS.opportunity) dto.opportunity = filters.opportunity;
  return dto;
}

function errorMessage(error: ApiError): string {
  switch (error.kind) {
    case "timeout":
      return "The recommendation request took too long and timed out. Try again.";
    case "server":
      return "The research directory API hit an error. Try again in a moment.";
    default:
      return error.message;
  }
}

function LoadingList() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading recommendations">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="card animate-pulse p-5">
          <div className="space-y-3">
            <div className="h-4 w-1/3 rounded bg-slate-200" />
            <div className="h-3 w-2/3 rounded bg-slate-100" />
            <div className="h-3 w-1/2 rounded bg-slate-100" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ForYouView() {
  const { profile, hydrated, saveError: profileError, retryLoad } = useStudentProfile();
  const [filters, setFilters] = useState<FilterValues>({ ...EMPTY_FILTERS });
  const [options, setOptions] = useState<Partial<FilterBarOptions>>({});

  const [results, setResults] = useState<Researcher[]>([]);
  const [matchById, setMatchById] = useState<Record<string, ResearcherMatch>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const requestSeq = useRef(0);
  const offsetRef = useRef(0);
  const filtersRef = useRef(filters);
  useLayoutEffect(() => { filtersRef.current = filters; }, [filters]);

  const ready = hydrated && hasResearchInterests(profile);
  const hasMore = results.length < total;

  const runRecommendations = useCallback(async (reset: boolean) => {
    const seq = ++requestSeq.current;
    const currentFilters = filtersRef.current;
    if (reset) {
      setError(null);
      setLoading(true);
    } else {
      setLoadingMore(true);
    }

    const start = reset ? 0 : offsetRef.current;
    try {
      const response = await getRecommendations(
        toProfileInput(profile),
        filtersToDto(currentFilters),
        { limit: PAGE_SIZE, offset: start },
      );
      if (seq !== requestSeq.current) return;

      const nextResearchers: Researcher[] = [];
      const nextMatches: Record<string, ResearcherMatch> = {};
      for (const row of response.results) {
        const { researcher, match } = toRecommendationResult(row);
        nextResearchers.push(researcher);
        nextMatches[String(row.researcher.id)] = match;
      }

      offsetRef.current = start + nextResearchers.length;
      setResults(reset ? nextResearchers : (previous) => [...previous, ...nextResearchers]);
      setMatchById((previous) => ({ ...previous, ...nextMatches }));
      setTotal(response.total);
      setError(null);
    } catch (caught) {
      if (seq !== requestSeq.current) return;
      const apiError =
        caught instanceof ApiError ? caught : new ApiError("unavailable", "Unexpected error");
      setError(apiError);
      if (reset) {
        setResults([]);
        setTotal(0);
      }
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [profile]);

  useEffect(() => {
    let cancelled = false;
    getSearchOptions()
      .then((data) => {
        if (!cancelled) setOptions(optionLists(data));
      })
      .catch(() => {
        /* filter options fall back to shipped lists */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(() => {
      void runRecommendations(true);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [ready, filters, runRecommendations]);

  if (!hydrated) {
    if (profileError) {
      return <><PageHeader title="Researchers recommended for you" /><div className="card mt-6 p-5" role="alert"><p>Could not load your research profile. {profileError}</p><Button variant="secondary" className="mt-3" onClick={retryLoad}>Try again</Button></div></>;
    }
    return (
      <>
        <PageHeader
          title="Researchers recommended for you"
          description="Based on your interests, skills, projects, coursework, and preferences."
        />
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <aside className="lg:col-span-1">
            <div className="card space-y-3 p-5">
              <div className="h-4 w-1/2 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-2/3 animate-pulse rounded bg-slate-100" />
              <div className="h-3 w-1/3 animate-pulse rounded bg-slate-100" />
            </div>
          </aside>
          <div className="lg:col-span-2">
            <LoadingList />
          </div>
        </div>
      </>
    );
  }

  if (!ready) {
    return (
      <>
        <PageHeader
          title="Researchers recommended for you"
          description="Based on your interests, skills, projects, coursework, and preferences."
        />
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <aside className="lg:col-span-1">
            <ProfileSummary profile={profile} compact />
          </aside>
          <div className="lg:col-span-2">
            <EmptyState
              icon={<Sparkles className="h-6 w-6" aria-hidden="true" />}
              title="Set up your profile to see matches"
              description="Pick at least one research interest so we can rank real professors against what you care about."
              action={<LinkButton href="/account/onboarding">Set up my profile</LinkButton>}
            />
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Researchers recommended for you"
        description="Based on matching interests, background, and preferred locations in the available researcher data."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-pill border border-brand-100 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Live research-fit ranking
          </span>
        }
      />

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <aside className="lg:col-span-1">
          <ProfileSummary profile={profile} compact />
        </aside>

        <div className="lg:col-span-2">
          <div className="space-y-5">
            <FilterBar values={filters} onChange={setFilters} options={options} />

            {loading ? (
              <LoadingList />
            ) : error ? (
              <div className="card p-6" role="alert">
                <div className="flex items-start gap-3">
                  <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
                  <div>
                    <h2 className="text-base font-semibold text-ink">
                      Recommendations are unavailable
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">{errorMessage(error)}</p>
                    <ErrorHelp />
                    <div className="mt-4">
                      <Button variant="secondary" onClick={() => void runRecommendations(true)}>
                        Try again
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            ) : total === 0 ? (
              <EmptyState
                icon={<SearchX className="h-6 w-6" aria-hidden="true" />}
                title={Object.keys(filtersToDto(filters)).length ? "No matches for these filters" : "No research matches for your profile yet"}
                description={Object.keys(filtersToDto(filters)).length
                  ? "Try clearing a filter, or broaden your interests in your profile."
                  : "Our current records may not cover your interests. Try related topics or explore the directory."}
                action={
                  Object.keys(filtersToDto(filters)).length ?
                    <Button variant="secondary" onClick={() => setFilters({ ...EMPTY_FILTERS })}>Reset filters</Button> :
                    <div className="flex flex-wrap justify-center gap-2"><LinkButton href="/account/onboarding" variant="secondary">Edit interests</LinkButton>
                      <LinkButton href={`/discover?q=${encodeURIComponent(profile.interests.join(" "))}`} variant="secondary">Explore researchers</LinkButton></div>
                }
              />
            ) : (
              <div className="flex flex-col gap-5">
                <p className="text-sm text-slate-500" aria-live="polite">
                  <span className="font-semibold text-ink">{total.toLocaleString()}</span>{" "}
                  {total === 1 ? "researcher" : "researchers"} matched
                </p>
                {results.map((researcher) => (
                  <div key={researcher.id} className="space-y-3">
                    <ResearcherRow researcher={researcher} match={matchById[researcher.id]} />
                    {matchById[researcher.id]?.reasons.length > 0 ? (
                      <WhyMatchPanel
                        match={matchById[researcher.id]}
                        researcherId={researcher.id}
                        researcher={researcher}
                        profile={toProfileInput(profile)}
                        enableAi
                        collapsible
                        defaultOpen={false}
                      />
                    ) : null}
                  </div>
                ))}
                {hasMore ? (
                  <div className="flex justify-center pt-2">
                    <Button
                      variant="secondary"
                      size="lg"
                      disabled={loadingMore}
                      onClick={() => void runRecommendations(false)}
                    >
                      {loadingMore ? "Loading…" : "Load more matches"}
                    </Button>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

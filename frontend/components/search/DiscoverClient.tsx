"use client";

import { useRouter } from "next/navigation";
import { SearchX, WifiOff } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ResearcherRow } from "@/components/researcher/ResearcherRow";
import { SearchBar } from "@/components/search/SearchBar";
import {
  EMPTY_FILTERS,
  FilterBar,
  type FilterBarOptions,
  type FilterValues,
} from "@/components/search/FilterBar";
import { Button, LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorHelp } from "@/components/ui/ErrorHelp";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiError } from "@/lib/api/client";
import { toMatch, toResearcher } from "@/lib/api/map";
import { getSearchOptions, searchResearchers } from "@/lib/api/researchers";
import type { OptionsDto } from "@/lib/api/types";
import type { Researcher, ResearcherMatch } from "@/types";

const PAGE_SIZE = 25;
const MAX_QUERY_LENGTH = 300;

// Keyed by the Discover URL so a saved offset is only reused for the search that
// produced it.
const SCROLL_KEY_PREFIX = "pf:discover-scroll:";

function scrollStorageKey(): string {
  return `${SCROLL_KEY_PREFIX}${window.location.pathname}${window.location.search}`;
}

const FILTER_KEYS = [
  "university",
  "field",
  "state",
  "verification",
  "opportunity",
] as const;

function seedFilters(initialFilters?: Partial<FilterValues>): FilterValues {
  const seeded = { ...EMPTY_FILTERS };
  for (const key of FILTER_KEYS) {
    const value = initialFilters?.[key];
    if (typeof value === "string" && value.trim()) {
      seeded[key] = value;
    }
  }
  return seeded;
}

function filterQueryString(query: string, filters: FilterValues): string {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  for (const key of FILTER_KEYS) {
    const value = filters[key];
    if (value && value !== EMPTY_FILTERS[key]) params.set(key, value);
  }
  return params.toString();
}

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

function errorMessage(error: ApiError): string {
  switch (error.kind) {
    case "timeout":
      return "The search took too long and timed out. Try again, or narrow your query.";
    case "server":
      return "The research directory API hit an error. Try again in a moment.";
    default:
      return error.message;
  }
}

export function DiscoverClient({
  initialQuery,
  initialFilters,
}: {
  initialQuery: string;
  initialFilters?: Partial<FilterValues>;
}) {
  const [draft, setDraft] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<FilterValues>(() => seedFilters(initialFilters));
  const [options, setOptions] = useState<Partial<FilterBarOptions>>({});

  const router = useRouter();

  const [results, setResults] = useState<Researcher[]>([]);
  const [matchById, setMatchById] = useState<Record<string, ResearcherMatch>>({});
  const [total, setTotal] = useState(0);
  const [mode, setMode] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const requestSeq = useRef(0);
  const offsetRef = useRef(0);
  const loadingMoreRef = useRef(false);
  const pendingScrollRef = useRef<number | null>(null);
  const paramsRef = useRef({ query, filters });
  useLayoutEffect(() => { paramsRef.current = { query, filters }; }, [query, filters]);

  const hasMore = results.length < total;
  const searchParams = filterQueryString(query, filters);
  const discoverHref = searchParams ? `/discover?${searchParams}` : "/discover";

  const syncUrl = useCallback(
    (nextQuery: string, nextFilters: FilterValues) => {
      const search = filterQueryString(nextQuery, nextFilters);
      const url = search ? `/discover?${search}` : "/discover";
      // Ignore late callbacks after navigation and avoid redundant replacements.
      if (window.location.pathname !== "/discover" || window.location.pathname + window.location.search === url) return;
      // Use the router rather than history.replaceState so Next keeps its own
      // URL state in step with the address bar. A raw replaceState leaves the
      // App Router believing the route is still the unfiltered /discover, so a
      // later Back navigation restores the stale URL and drops the query and
      // filters. `replace` keeps one history entry for the search itself while
      // still letting Back return from a profile to this exact search.
      router.replace(url, { scroll: false });
    },
    [router],
  );

  const runSearch = useCallback(
    async (reset: boolean) => {
      if (!reset && loadingMoreRef.current) return;
      const seq = ++requestSeq.current;
      const { query: currentQuery, filters: currentFilters } = paramsRef.current;
      if (reset) {
        loadingMoreRef.current = false;
        setError(null);
        setLoading(true);
        syncUrl(currentQuery, currentFilters);
      } else {
        loadingMoreRef.current = true;
        setLoadingMore(true);
      }

      const start = reset ? 0 : offsetRef.current;
      try {
        const response = await searchResearchers({
          query: currentQuery,
          university: currentFilters.university,
          state: currentFilters.state,
          field: currentFilters.field,
          verification: currentFilters.verification,
          opportunity: currentFilters.opportunity,
          limit: PAGE_SIZE,
          offset: start,
        });
        if (seq !== requestSeq.current) return;

        const nextResults = response.results.map((row) => toResearcher(row.researcher));
        const nextMatches: Record<string, ResearcherMatch> = {};
        for (const row of response.results) {
          const match = toMatch(row.match);
          if (match) nextMatches[String(row.researcher.id)] = match;
        }

        const nextOffset = start + response.results.length;
        offsetRef.current = nextOffset;
        setResults((previous) => {
          if (reset) return nextResults;
          const seen = new Set(previous.map((item) => item.id));
          return [...previous, ...nextResults.filter((item) => !seen.has(item.id))];
        });
        // Reset replaces the match map so a query-specific reason can never
        // leak into a later, unrelated search (for example after clearing the
        // query). Appending merges into the existing map.
        setMatchById((previous) => (reset ? nextMatches : { ...previous, ...nextMatches }));
        setTotal(response.total);
        setMode(response.mode);
        setError(null);
      } catch (caught) {
        if (seq !== requestSeq.current) return;
        const apiError =
          caught instanceof ApiError ? caught : new ApiError("unavailable", "Unexpected error");
        setError(apiError);
        if (reset) {
          setResults([]);
          setMatchById({});
          setTotal(0);
        }
      } finally {
        if (seq === requestSeq.current) {
          setLoading(false);
          setLoadingMore(false);
        }
        if (!reset) loadingMoreRef.current = false;
      }
    },
    [syncUrl],
  );

  const clearSearch = useCallback(() => {
    setDraft("");
    setQuery("");
    setFilters({ ...EMPTY_FILTERS });
  }, []);

  useEffect(() => {
    let cancelled = false;
    getSearchOptions()
      .then((data) => {
        if (!cancelled) setOptions(optionLists(data));
      })
      .catch(() => {
        /* filter options fall back to the shipped fixture lists */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Claim the offset saved when this search was left for a profile.
  useEffect(() => {
    try {
      const stored = window.sessionStorage.getItem(scrollStorageKey());
      if (stored !== null) {
        window.sessionStorage.removeItem(scrollStorageKey());
        const parsed = Number(stored);
        if (Number.isFinite(parsed) && parsed > 0) pendingScrollRef.current = parsed;
      }
    } catch {
      /* storage unavailable */
    }
  }, []);

  // Save the offset before any navigation into a profile.
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as HTMLElement | null)?.closest?.("a");
      if (!anchor?.getAttribute("href")?.startsWith("/researchers/")) return;
      try {
        window.sessionStorage.setItem(scrollStorageKey(), String(Math.round(window.scrollY)));
      } catch {
        /* storage unavailable */
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  // The results render in stages and the skeleton is shorter than the loaded
  // list, so the browser's own restore lands on a collapsed offset. Re-apply it
  // once the cards are actually in the DOM.
  useEffect(() => {
    const target = pendingScrollRef.current;
    if (loading || target === null || results.length === 0) return;
    pendingScrollRef.current = null;
    const timer = window.setTimeout(() => window.scrollTo(0, target), 60);
    return () => window.clearTimeout(timer);
  }, [loading, results]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void runSearch(true);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query, filters, runSearch]);

  return (
    <Container className="py-10 sm:py-12">
      <PageHeader
        title="Discover researchers"
        description="Search by research area, question, problem, or topic in your own words. No profile needed."
      />

      <div className="mt-8 space-y-5">
        <SearchBar
          align="start"
          value={draft}
          onValueChange={setDraft}
          maxLength={MAX_QUERY_LENGTH}
          onSearch={(next) => {
            setDraft(next);
            setQuery(next);
          }}
        />

        <FilterBar values={filters} onChange={setFilters} options={options} />

        {loading ? (
          <div className="space-y-4" aria-busy="true" aria-label="Loading results">
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
        ) : error ? (
          error.kind === "invalid" ? (
            <div className="card p-6" role="alert">
              <div className="flex items-start gap-3">
                <SearchX className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" aria-hidden="true" />
                <div>
                  <h2 className="text-base font-semibold text-ink">Check your search</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    That search could not be processed. Keep it under {MAX_QUERY_LENGTH}{" "}
                    characters and try again.
                  </p>
                  <div className="mt-4">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        clearSearch();
                        document.getElementById("search-input")?.focus();
                      }}
                    >
                      Clear and edit search
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="card p-6" role="alert">
              <div className="flex items-start gap-3">
                <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    {error.kind === "rate-limited" ? "Please wait before searching again" : "Search is unavailable"}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">{errorMessage(error)}</p>
                  <ErrorHelp />
                  <div className="mt-4">
                    <Button variant="secondary" onClick={() => void runSearch(true)}>
                      Try again
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )
        ) : (
          <>
            <p className="break-words text-sm text-slate-500" aria-live="polite">
              <span className="font-semibold text-ink">{total.toLocaleString()}</span>{" "}
              {total === 1 ? "researcher" : "researchers"} found
              {query.trim() ? (
                <>
                  {" "}
                  for{" "}
                  <span className="break-all font-medium text-ink-600">“{query.trim()}”</span>
                </>
              ) : null}
              {mode === "AI semantic + keyword" ? (
                <span className="ml-1.5 rounded-pill border border-brand-200 bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                  semantic + keyword
                </span>
              ) : null}
            </p>

            {total === 0 ? (
              <EmptyState
                icon={<SearchX className="h-6 w-6" aria-hidden="true" />}
                title="No researchers match those filters"
                description="Try a broader query or clear a filter."
                action={
                  <Button variant="secondary" onClick={clearSearch}>
                    Clear search
                  </Button>
                }
              />
            ) : (
              <div className="flex flex-col gap-4">
                {results.map((researcher) => (
                  <ResearcherRow
                    key={researcher.id}
                    researcher={researcher}
                    profileHref={`/researchers/${researcher.id}?returnTo=${encodeURIComponent(discoverHref)}`}
                    match={matchById[researcher.id]}
                  />
                ))}
                {hasMore ? (
                  <div className="flex justify-center pt-2">
                    <Button
                      variant="secondary"
                      size="lg"
                      disabled={loadingMore}
                      onClick={() => void runSearch(false)}
                    >
                      {loadingMore ? "Loading…" : "Load more researchers"}
                    </Button>
                  </div>
                ) : null}
                {loadingMore ? (
                  <div className="card animate-pulse p-5" aria-hidden="true">
                    <div className="h-4 w-1/3 rounded bg-slate-200" />
                  </div>
                ) : null}
              </div>
            )}
          </>
        )}

        <div className="panel-aqua flex flex-col items-start justify-between gap-3 p-5 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-semibold text-accent-700">Want more personalized results?</p>
            <p className="mt-1 text-sm text-ink-600">
              Build a short research profile and see researchers ranked against what you care about.
            </p>
          </div>
          <LinkButton href="/account/onboarding" size="sm">
            Build my profile
          </LinkButton>
        </div>
      </div>
    </Container>
  );
}

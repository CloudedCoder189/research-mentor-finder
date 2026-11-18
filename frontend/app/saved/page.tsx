"use client";

import { BookmarkX, Mail, MailPlus, RotateCcw, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { ResearcherRow } from "@/components/researcher/ResearcherRow";
import { useSaved } from "@/components/saved/SavedProvider";
import { ShortlistComparison } from "@/components/saved/ShortlistComparison";
import { useAuth } from "@/lib/auth-context";
import { useComparisonSelection } from "@/lib/comparisonSelection";
import {
  EMPTY_FILTERS,
  FilterBar,
  type FilterBarOptions,
  type FilterValues,
} from "@/components/search/FilterBar";
import { Badge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorHelp } from "@/components/ui/ErrorHelp";
import { PageHeader } from "@/components/ui/PageHeader";
import { getSearchOptions } from "@/lib/api/researchers";
import { fieldFilterMatches, opportunityFilterMatches } from "@/lib/fieldFilters";
import { OUTREACH_STATUSES } from "@/lib/meta";
import type { OptionsDto } from "@/lib/api/types";
import type { OutreachStatus } from "@/types";

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

export default function SavedPage() {
  const { user } = useAuth();
  return <SavedAccountPage key={user?.user_id ?? "signed-out"} account={user?.user_id} />;
}

function SavedAccountPage({ account }: { account?: string }) {
  const { rows, status, error, refresh, remove } = useSaved();
  const { selected: storedSelection, setSelected } = useComparisonSelection(account);
  const selected = storedSelection.filter(id => rows.some(row => row.researcher.id === id));
  const [comparing, setComparing] = useState(false);
  const [comparisonStarted, setComparisonStarted] = useState(false);
  const comparisonRows = selected.flatMap(id => rows.filter(row => row.researcher.id === id));
  const toggleComparison = (id: string) => setSelected(selected.includes(id) ? selected.filter(value => value !== id) : selected.length < 3 ? [...selected, id] : selected);
  const [filters, setFilters] = useState<FilterValues>({ ...EMPTY_FILTERS });
  const [options, setOptions] = useState<Partial<FilterBarOptions>>({});
  const [removing, setRemoving] = useState<string | null>(null);

  // Load the same option lists Discover uses. Without this the field menu fell
  // back to the shipped seed fixture, whose labels ("Statistics & Data
  // Science") are not taxonomy values, so choosing one could never match a
  // real record's field.
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

  const saved = useMemo(() => {
    return rows.filter(({ researcher }) => {
      if (filters.university !== EMPTY_FILTERS.university && researcher.university !== filters.university)
        return false;
      // Broad categories ("Computing") select records whose discipline matches,
      // not only records whose field label is identical.
      if (filters.field !== EMPTY_FILTERS.field && !fieldFilterMatches(researcher, filters.field))
        return false;
      if (filters.state !== EMPTY_FILTERS.state && researcher.state !== filters.state) return false;
      if (filters.verification !== EMPTY_FILTERS.verification && researcher.verificationStatus !== filters.verification) return false;
      if (!opportunityFilterMatches(researcher.opportunityLevel, filters.opportunity)) return false;
      return true;
    });
  }, [rows, filters]);

  const filtersActive = Object.keys(filters).some(
    (key) => filters[key as keyof FilterValues] !== EMPTY_FILTERS[key as keyof FilterValues],
  );

  const statusSummary = useMemo(() => {
    const counts = new Map<OutreachStatus, number>();
    for (const { outreach } of saved) {
      counts.set(outreach.status, (counts.get(outreach.status) ?? 0) + 1);
    }
    return counts;
  }, [saved]);

  const onRemove = (id: string) => {
    setRemoving(id);
    void remove(id).then(removed => { if (removed) setSelected(current => current.filter(value => value !== id)); }).finally(() => setRemoving(null));
  };

  return (
    <RequireAuth>
      <Container className="py-10 sm:py-12">
      <PageHeader
        title="Saved researchers"
        description="Researchers you’ve saved for later or want to consider contacting."
      />

      {status === "loading" || status === "error" ? (
        <>
          <div className="mt-6">
            <FilterBar values={filters} onChange={setFilters} options={options} />
          </div>
          {status === "loading" ? (
            <div className="card mt-6 animate-pulse p-5" aria-hidden="true">
              <div className="h-4 w-2/3 rounded bg-slate-200" />
              <div className="mt-4 h-4 w-1/2 rounded bg-slate-200" />
            </div>
          ) : (
            <div className="card mt-6 p-6" role="alert">
              <div className="flex items-start gap-3">
                <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" />
                <div>
                  <h2 className="text-base font-semibold text-ink">Saved list is unavailable</h2>
                  <p className="mt-1 text-sm text-slate-500">{error}</p>
                  <ErrorHelp />
                  <div className="mt-4">
                    <Button variant="secondary" onClick={() => void refresh()}>
                      Try again
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          {rows.length > 0 ? <div className="card mt-6 p-5">
            <h2 className="font-semibold">Build a comparison</h2>
            <p className="mt-2 text-sm text-slate-500">Choose 2–3 saved researchers. Selections stay in this browser tab and clear when you sign out.</p>
            <p className="mt-2 text-sm" role="status">{comparisonRows.length} of 3 selected{comparisonRows.length ? `: ${comparisonRows.map(row => row.researcher.name).join(", ")}` : ""}</p>
            <div className="mt-3 flex flex-wrap gap-2"><Button disabled={comparisonRows.length < 2} onClick={() => { setComparisonStarted(true); setComparing(true); }}>Compare selected</Button><Button variant="secondary" disabled={!selected.length} onClick={() => { setSelected([]); setComparing(false); setComparisonStarted(false); }}>Clear comparison</Button>{comparing ? <Button variant="secondary" onClick={() => setComparing(false)}>Hide comparison</Button> : null}</div>
            {selected.length === 3 ? <p className="mt-2 text-sm">Three selected. Remove one to choose another.</p> : null}
          </div> : null}
          {comparisonStarted && comparisonRows.length ? <div hidden={!comparing}><ShortlistComparison rows={comparisonRows} onRemove={id => setSelected(current => current.filter(value => value !== id))} /></div> : null}
          {rows.length > 0 ? (
            <div className="mt-6 flex flex-wrap gap-2" aria-label="Outreach summary">
              {OUTREACH_STATUSES.map((statusName) => {
                const count = statusSummary.get(statusName) ?? 0;
                if (count === 0) return null;
                return (
                  <Badge
                    key={statusName}
                    tone="neutral"
                    className="border-slate-200 bg-slate-50 text-slate-600"
                  >
                    {statusName}: {count}
                  </Badge>
                );
              })}
            </div>
          ) : null}

          <div className="mt-6">
            <FilterBar values={filters} onChange={setFilters} options={options} />
          </div>

          {saved.length === 0 ? (
            rows.length === 0 ? (
              <EmptyState
                icon={<BookmarkX className="h-6 w-6" aria-hidden="true" />}
                title="Nothing saved yet"
                description="Save researchers from Discover or For You to build a shortlist for outreach."
                action={<LinkButton href="/discover">Browse researchers</LinkButton>}
              />
            ) : (
              // The shortlist is not empty: the active filters simply exclude
              // every saved record. Saying "nothing saved yet" here would deny
              // a shortlist the user can see by resetting.
              <EmptyState
                icon={<BookmarkX className="h-6 w-6" aria-hidden="true" />}
                title="No saved researchers match these filters"
                description={`You have ${rows.length} saved ${rows.length === 1 ? "researcher" : "researchers"}, but none match the filters you selected.`}
                action={
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setFilters({ ...EMPTY_FILTERS })}
                    disabled={!filtersActive}
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                    Reset filters
                  </Button>
                }
              />
            )
          ) : (
            <div className="mt-6 flex flex-col gap-4">
              {saved.map(({ researcher, outreach }) => {
                const hasDraft =
                  outreach.status === "Drafted" || outreach.status === "Sent";
                return (
                  <ResearcherRow
                    key={researcher.id}
                    researcher={researcher}
                    outreachStatus={outreach.status}
                    showSave={false}
                    hideProfileLink
                    extraActions={
                      <>
                        <Button type="button" size="sm" variant="secondary" aria-pressed={selected.includes(researcher.id)} aria-label={`Compare ${researcher.name}`} disabled={!selected.includes(researcher.id) && selected.length >= 3} onClick={() => toggleComparison(researcher.id)}>{selected.includes(researcher.id) ? "Selected for comparison" : "Compare"}</Button>
                        <LinkButton
                          href={`/outreach/compose/${researcher.id}`}
                          variant={hasDraft ? "primary" : "secondary"}
                          size="sm"
                        >
                          {hasDraft ? (
                            <>
                              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                              Continue draft
                            </>
                          ) : (
                            <>
                              <MailPlus className="h-3.5 w-3.5" aria-hidden="true" />
                              Draft outreach
                            </>
                          )}
                        </LinkButton>
                        <Button
                          type="button"
                          variant="danger"
                          size="sm"
                          disabled={removing === researcher.id}
                          onClick={() => onRemove(researcher.id)}
                          aria-label={`Remove ${researcher.name} from saved`}
                        >
                          {removing === researcher.id ? "Removing…" : "Remove"}
                        </Button>
                      </>
                    }
                  />
                );
              })}
            </div>
          )}
        </>
      )}
      </Container>
    </RequireAuth>
  );
}

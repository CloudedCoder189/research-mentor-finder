"use client";

import { useEffect, useMemo, useState } from "react";
import { MatchEvidence, safeSourceUrl } from "@/components/researcher/MatchEvidence";
import { WhyMatchPanel } from "@/components/researcher/WhyMatchPanel";
import { Button, LinkButton } from "@/components/ui/Button";
import { getResearcherProfile } from "@/lib/api/researchers";
import { explainMatch } from "@/lib/api/recommendations";
import { toProfileInput, toProfileResearcher, toRecommendationMatch } from "@/lib/api/map";
import type { ProfileInputDto, ResearcherProfileDto } from "@/lib/api/types";
import { useStudentProfile } from "@/lib/useStudentProfile";
import type { ResearcherMatch, SavedResult } from "@/types";

export function ShortlistComparison({ rows, onRemove }: { rows: SavedResult[]; onRemove: (id: string) => void }) {
  const { profile, hydrated, saveError, retryLoad } = useStudentProfile();
  const serialized = JSON.stringify(toProfileInput(profile));
  const input = useMemo(() => JSON.parse(serialized) as ProfileInputDto, [serialized]);
  return <section aria-labelledby="comparison-title" className="mt-6">
    <h2 id="comparison-title" className="text-xl font-semibold">Compare your shortlist</h2>
    <p className="mt-2 text-sm text-slate-500">Compare research relevance and check the sources. A match does not establish student eligibility or an open position.</p>
    {saveError ? <div className="mt-3" role="alert"><p>Your profile could not be loaded. Research details remain available.</p><Button variant="secondary" onClick={retryLoad}>Retry profile</Button></div> : !hydrated ? <p className="mt-3" role="status">Loading your research profile…</p> : null}
    <div className="mt-4 grid min-w-0 gap-4 lg:grid-cols-3">
      {rows.map(row => <ComparisonCard key={`${row.researcher.id}:${serialized}:${hydrated}`} row={row} profile={hydrated && !saveError ? input : null} onRemove={onRemove} />)}
    </div>
  </section>;
}

function ComparisonCard({ row, profile, onRemove }: { row: SavedResult; profile: ProfileInputDto | null; onRemove: (id: string) => void }) {
  const [details, setDetails] = useState<ResearcherProfileDto | null>(null);
  const [match, setMatch] = useState<ResearcherMatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const id = row.researcher.id;
  const hasInterests = Boolean(profile?.interests.length || profile?.interest_text?.trim());
  useEffect(() => {
    let cancelled = false;
    const fit = profile && hasInterests ? explainMatch(profile, id, { includeAi: false }) : Promise.resolve(null);
    Promise.allSettled([getResearcherProfile(id), fit]).then(([detailResult, fitResult]) => {
      if (cancelled) return;
      if (detailResult.status === "fulfilled") setDetails(detailResult.value); else setError(true);
      if (fitResult.status === "fulfilled" && fitResult.value?.results[0]) setMatch(toRecommendationMatch(fitResult.value.results[0].match));
      else if (fitResult.status === "rejected") setError(true);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [id, profile, hasInterests, attempt]);
  const researcher = details ? toProfileResearcher(details) : row.researcher;
  const source = safeSourceUrl(researcher.sourceUrl);
  return <article aria-label={`Compare ${researcher.name}`} className="card min-w-0 break-words p-5">
    <h3 className="text-lg font-semibold">{researcher.name}</h3>
    <p className="mt-1 text-sm">{researcher.title || "Title unavailable"}</p>
    <p className="mt-2 text-sm text-slate-500">{researcher.university} · {[researcher.city, researcher.state].filter(Boolean).join(", ") || "Location unavailable"}</p>
    <dl className="mt-4 space-y-3 text-sm">
      <div><dt className="font-semibold">Research area</dt><dd>{researcher.field || "Not available"}</dd></div>
      <div><dt className="font-semibold">Research focus</dt><dd className="whitespace-pre-line">{researcher.researchInterests || "Not available"}</dd></div>
      <div><dt className="font-semibold">Record check</dt><dd>{researcher.verificationStatus} · {details?.last_checked_at || "Check date unavailable"}</dd></div>
      <div><dt className="font-semibold">Profile evidence</dt><dd>{details?.opportunity_signals || "No specific profile evidence recorded. Check the source and ask the researcher."}</dd></div>
    </dl>
    {loading ? <p className="mt-4 text-sm" role="status">Loading details and research fit…</p> : null}
    {error ? <div className="mt-4 text-sm" role="alert"><p>Some comparison details could not load. Saved information is shown.</p><Button size="sm" variant="secondary" onClick={() => { setLoading(true); setError(false); setDetails(null); setMatch(null); setAttempt(n => n + 1); }}>Retry comparison</Button></div> : null}
    {match ? <div className="mt-4"><WhyMatchPanel match={match} /><MatchEvidence researcher={researcher} match={match} /></div> : !loading && profile && !hasInterests ? <LinkButton href="/account/onboarding" size="sm" variant="secondary">Add interests for fit reasons</LinkButton> : null}
    {source ? <a className="focus-ring mt-4 inline-block rounded-control text-sm text-brand-700 underline" href={source} target="_blank" rel="noopener noreferrer">Review original source</a> : <p className="mt-4 text-sm text-slate-500">Source link not available.</p>}
    <div className="mt-4 flex flex-wrap gap-2">
      <LinkButton href={`/researchers/${id}`} size="sm" variant="secondary">Open profile</LinkButton>
      <LinkButton href={`/outreach/compose/${id}`} size="sm" variant="secondary">Prepare draft</LinkButton>
      <Button size="sm" variant="secondary" onClick={() => onRemove(id)} aria-label={`Remove ${researcher.name} from comparison`}>Remove from comparison</Button>
    </div>
  </article>;
}

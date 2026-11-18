import type { Researcher, ResearcherMatch } from "@/types";

export function safeSourceUrl(value?: string | null): string | null {
  if (!value) return null;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : null; } catch { return null; }
}

export function MatchEvidence({ researcher, match }: { researcher: Researcher; match: ResearcherMatch }) {
  const source = safeSourceUrl(researcher.sourceUrl);
  return <details className="mt-4 border-t border-border pt-3 text-sm">
    <summary className="focus-ring cursor-pointer rounded-control font-medium text-ink">Evidence behind this match</summary>
    <p className="mt-3 text-slate-500">These are signals from stored researcher information, not verified quotations or evidence of an open position.</p>
    {match.signals?.length ? <ul className="mt-3 space-y-2">
      {match.signals.map((signal, index) => <li key={index} className="break-words"><strong>{signal.label}:</strong> {signal.detail}{signal.topic ? <> → matched topic: {signal.topic}</> : null}</li>)}
    </ul> : <p className="mt-3">No specific matching signals were recorded.</p>}
    <p className="mt-3 font-medium">Stored research information</p>
    <p className="mt-1 whitespace-pre-line break-words">{researcher.researchInterests || "Research details not available."}</p>
    {researcher.researchOverview ? <p className="mt-3 break-words text-slate-500">Generated summary, not a source quotation: {researcher.researchOverview}</p> : null}
    {source ? <a className="focus-ring mt-3 inline-block rounded-control text-brand-700 underline" href={source} target="_blank" rel="noopener noreferrer">Review original source</a> : <p className="mt-3 text-slate-500">Source link not available.</p>}
  </details>;
}

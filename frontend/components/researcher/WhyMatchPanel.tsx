"use client";

import { CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { MatchBadge } from "@/components/researcher/MatchBadge";
import { MatchEvidence } from "@/components/researcher/MatchEvidence";
import { toRecommendationResult } from "@/lib/api/map";
import { explainMatch } from "@/lib/api/recommendations";
import type { ProfileInputDto } from "@/lib/api/types";
import type { Researcher, ResearcherMatch } from "@/types";

type ExplanationStatus = "idle" | "loading" | "done" | "error";

export function WhyMatchPanel({
  match,
  collapsible = false,
  defaultOpen = false,
  className,
  researcherId,
  profile,
  enableAi = false,
  researcher,
}: {
  match: ResearcherMatch;
  collapsible?: boolean;
  defaultOpen?: boolean;
  className?: string;
  researcherId?: string;
  profile?: ProfileInputDto;
  enableAi?: boolean;
  researcher?: Researcher;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [status, setStatus] = useState<ExplanationStatus>("idle");
  const [explained, setExplained] = useState<ResearcherMatch | null>(null);
  const identity = `${researcherId}:${JSON.stringify(profile)}`;
  const activeIdentity = useRef(identity);
  useLayoutEffect(() => { activeIdentity.current = identity; }, [identity]);
  const requestId = useRef(0);
  const pending = useRef(false);

  useEffect(() => {
    requestId.current += 1;
    pending.current = false;
    setExplained(null);
    setStatus("idle");
    return () => { requestId.current += 1; };
  }, [identity]);

  async function requestExplanation() {
    if (!enableAi || !researcherId || !profile || pending.current || (status !== "idle" && status !== "error")) return;
    const currentRequest = ++requestId.current;
    const currentIdentity = identity;
    pending.current = true;
    setStatus("loading");
    try {
      const response = await explainMatch(profile, researcherId, { includeAi: true });
      if (currentRequest !== requestId.current || currentIdentity !== activeIdentity.current) return;
      if (response.results.length > 0) {
        const result = toRecommendationResult(response.results[0]).match;
        setExplained(result);
        setStatus(["timeout", "error", "invalid"].includes(result.aiExplanation?.status ?? "") ? "error" : "done");
      } else {
        setStatus("error");
      }
    } catch {
      if (currentRequest === requestId.current && currentIdentity === activeIdentity.current) setStatus("error");
    } finally {
      if (currentRequest === requestId.current) pending.current = false;
    }
  }

  function handleToggle() {
    const next = !open;
    setOpen(next);
    if (next) void requestExplanation();
  }

  if (!collapsible) {
    return <div><WhyMatchBody match={match} className={className} />{researcher ? <MatchEvidence researcher={researcher} match={match} /> : null}</div>;
  }

  return (
    <div className={`panel-aqua ${className ?? ""}`}>
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={open}
        className="focus-ring flex w-full cursor-pointer list-none items-center justify-between gap-2 px-4 py-2.5 text-left text-sm font-medium text-accent-700"
      >
        <span className="inline-flex items-center gap-2">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Why you match
        </span>
        <span className="text-xs font-normal text-slate-500">
          {open ? "Hide" : "Show reasons"}
        </span>
      </button>
      {open ? (
        <div className="px-4 pb-4">
          {status === "loading" ? (
            <div
              className="flex items-center gap-2 text-sm text-slate-500"
              aria-busy="true"
            >
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Personalizing…
            </div>
          ) : null}
          <WhyMatchBody match={explained ?? match} />
          {researcher ? <MatchEvidence researcher={researcher} match={explained ?? match} /> : null}
          {status === "error" ? (
            <div className="mt-3 text-sm" role="alert">
              <p>AI explanation is unavailable. Your research-fit reasons are shown above.</p>
              <button type="button" className="focus-ring mt-2 rounded-control underline" onClick={() => void requestExplanation()}>Try explanation again</button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function WhyMatchBody({ match, className }: { match: ResearcherMatch; className?: string }) {
  const ai = match.aiExplanation;
  const personalized = Boolean(ai && ai.source === "ai" && ai.reasons.length > 0);
  const reasons = personalized && ai ? ai.reasons : match.reasons;

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-ink">
          {personalized ? "Personalized explanation" : "Why you match"}
        </span>
        <MatchBadge label={match.label} />
      </div>
      <ul className="mt-3 space-y-2">
        {reasons.map((reason, index) => (
          <li key={index} className="flex items-start gap-2 text-sm text-ink-600">
            <CheckCircle2
              className="mt-0.5 h-4 w-4 shrink-0 text-accent-600"
              aria-hidden="true"
            />
            {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

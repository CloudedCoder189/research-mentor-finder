import Link from "next/link";
import type { Researcher } from "@/types";
import { RESEARCH_DIRECTIONS } from "@/data/researchDirections";
import { safeSourceUrl, suggestDirections } from "@/lib/researchLearning";
import { DirectionGuide } from "./DirectionGuide";

export function ProfileResearchGuide({ researcher }: { researcher: Researcher }) {
  const directions = suggestDirections(researcher.researchInterests, RESEARCH_DIRECTIONS);
  const source = safeSourceUrl(researcher.sourceUrl) || safeSourceUrl(researcher.profileUrl || "");
  return <section className="card p-5 sm:p-6" aria-labelledby="understand-research-title">
    <h2 id="understand-research-title" className="text-xl font-semibold text-ink-950">Understand this research</h2><p className="mt-3 text-sm text-ink-600">Use the recorded research interests above as a starting point. These guides explain related fields; they do not establish this lab&apos;s exact methods or summarize a paper we have not read.</p>
    {directions.length ? <div className="mt-4 space-y-3">{directions.map((direction) => <details key={direction.id} className="rounded-control border border-border p-4"><summary className="focus-ring cursor-pointer rounded-control font-semibold">Learn about {direction.title.toLowerCase()}</summary><div className="mt-4"><DirectionGuide direction={direction} /></div></details>)}</div> : <p className="mt-4 text-sm text-slate-500">We do not yet have a field guide confidently linked to these interests. Review the original source and ask which questions and methods the group currently studies.</p>}
    <div className="mt-5"><h3 className="font-semibold">Read with a question in mind</h3><ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-ink-600"><li>What question is this group trying to answer?</li><li>Which measurements, sources or methods support the work?</li><li>What limits or uncertainty does the source describe?</li><li>What would you genuinely like to understand better?</li></ol>{source ? <a href={source} target="_blank" rel="noopener noreferrer" className="focus-ring mt-3 inline-block rounded-control text-sm font-medium text-brand-700 underline">Review {researcher.name}&apos;s original source</a> : null}</div>
    <div className="mt-6 rounded-control border border-border p-4"><h3 className="font-semibold">Individual mentoring availability: unknown</h3><p className="mt-2 text-sm text-ink-600">An academic profile or research match does not confirm that this researcher is accepting students of your level. We have no explicit individual availability confirmation for this profile.</p><Link href="/opportunities?mentoring=1" className="focus-ring mt-3 inline-block rounded-control text-sm font-medium text-brand-700 underline">Check source-confirmed mentoring pathways</Link><p className="mt-3 text-xs text-slate-500">Before committing, ask about the appropriate contact, daily supervision, time commitment, eligibility and expected activities.</p></div>
  </section>;
}

import Link from "next/link";
import type { ResearchDirection } from "@/data/researchDirections";
import { researcherSearchHref } from "@/lib/researchLearning";

export function DirectionGuide({ direction }: { direction: ResearchDirection }) {
  return <div className="space-y-5">
    <div><h3 className="font-semibold text-ink">A question in this area</h3><p className="mt-2 text-sm text-ink-600">{direction.question}</p></div>
    <div><h3 className="font-semibold text-ink">How researchers might approach it</h3><p className="mt-2 text-sm leading-relaxed text-ink-600">{direction.approach}</p><p className="mt-2 text-xs text-slate-500">General learning guidance. Check a researcher&apos;s source to understand their particular methods.</p></div>
    <dl className="grid gap-3 sm:grid-cols-2">{direction.terms.map((item) => <div key={item.term} className="rounded-control border border-border p-3"><dt className="font-medium text-ink">{item.term}</dt><dd className="mt-1 text-sm text-ink-600">{item.meaning}</dd></div>)}</dl>
    <div className="flex flex-wrap gap-3 text-sm"><Link href={researcherSearchHref(direction.query)} className="focus-ring rounded-control font-medium text-brand-700 underline">Explore relevant researchers</Link><a href={direction.source.url} target="_blank" rel="noopener noreferrer" className="focus-ring rounded-control text-brand-700 underline">{direction.source.label} <span className="sr-only">(opens in a new tab)</span></a></div>
  </div>;
}

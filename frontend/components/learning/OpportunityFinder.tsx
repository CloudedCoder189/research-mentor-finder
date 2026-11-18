"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RESEARCH_OPPORTUNITIES } from "@/data/researchOpportunities";
import { RESEARCH_DIRECTIONS } from "@/data/researchDirections";
import { matchesConcept, opportunityStatus, schoolFit } from "@/lib/researchLearning";
import { Container } from "@/components/ui/Container";
import { LearningIntro } from "./LearningIntro";
import { Button } from "@/components/ui/Button";

export function OpportunityFinder({ initialDirection = "", initialMentoring = false, initialNow }: { initialDirection?: string; initialMentoring?: boolean; initialNow: string }) {
  const [direction, setDirection] = useState(initialDirection);
  const [level, setLevel] = useState("");
  const [format, setFormat] = useState("");
  const [mentoring, setMentoring] = useState(initialMentoring);
  const [hideDifferent, setHideDifferent] = useState(false);
  const [query, setQuery] = useState("");
  const [now, setNow] = useState(() => new Date(initialNow));
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 60000); return () => window.clearInterval(timer); }, []);
  const guide = RESEARCH_DIRECTIONS.find((row) => row.id === direction);
  const rows = RESEARCH_OPPORTUNITIES.filter((row) =>
    (!guide || row.topics.some((topic) => topic === guide.id || guide.keywords.some((word) => matchesConcept(topic, word)))) &&
    (!format || row.format === format || row.format === "Varies") &&
    (!mentoring || row.kind !== "Public contribution") &&
    (!hideDifferent || schoolFit(row, level) !== "different-level") &&
    (!query.trim() || `${row.name} ${row.description} ${row.topics.join(" ")} ${row.location}`.toLowerCase().includes(query.trim().toLowerCase()))
  );
  function reset() { window.history.replaceState(window.history.state, "", "/opportunities"); setDirection(""); setLevel(""); setFormat(""); setMentoring(false); setHideDifferent(false); setQuery(""); }
  return <Container className="[overflow-wrap:anywhere] py-8 sm:py-12">
    <LearningIntro kind="opportunities" eyebrow="Real sources, practical choices" title="Research opportunities and mentor pathways">Explore a small, reviewed collection of programmes, discovery routes and public activities. Check the provider&apos;s current requirements before applying.</LearningIntro>
    <div className="card mt-6 grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4" aria-label="Opportunity filters">
      <div><label htmlFor="opportunity-query" className="block text-sm font-medium">Search this collection</label><input id="opportunity-query" type="search" maxLength={100} value={query} onChange={(e) => setQuery(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3" /></div>
      <div><label htmlFor="opportunity-direction" className="block text-sm font-medium">Research direction</label><select id="opportunity-direction" value={direction} onChange={(e) => setDirection(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3"><option value="">Any direction</option>{RESEARCH_DIRECTIONS.map((row) => <option key={row.id} value={row.id}>{row.title}</option>)}</select></div>
      <div><label htmlFor="opportunity-level" className="block text-sm font-medium">School level</label><select id="opportunity-level" value={level} onChange={(e) => setLevel(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3"><option value="">Not specified</option><option value="hs-younger">High school: grades 9-10</option><option value="hs-junior">High school junior</option><option value="hs-senior">High school senior</option><option value="entering-college">Graduated and accepted into college</option><option value="college">College undergraduate</option></select></div>
      <div><label htmlFor="opportunity-format" className="block text-sm font-medium">Format</label><select id="opportunity-format" value={format} onChange={(e) => setFormat(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3"><option value="">Any format</option><option value="In person">In person</option><option value="Online activities">Online activities</option></select><p className="mt-1 text-xs text-slate-500">Routes with mixed formats stay visible.</p></div>
      <div className="flex flex-wrap gap-4 sm:col-span-2 lg:col-span-4"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={mentoring} onChange={(e) => setMentoring(e.target.checked)} className="focus-ring h-4 w-4" />Mentored program pathways only</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={hideDifferent} onChange={(e) => setHideDifferent(e.target.checked)} className="focus-ring h-4 w-4" />Hide routes with a different school level</label><Button variant="secondary" size="sm" onClick={reset}>Reset opportunity filters</Button></div>
    </div>
    <p className="mt-4 text-sm text-slate-500" role="status">{rows.length} {rows.length === 1 ? "route" : "routes"} in this reviewed collection. School level alone does not establish eligibility.</p>
    <section className="panel-aqua mt-5 p-5" aria-labelledby="mentor-evidence"><h2 id="mentor-evidence" className="font-semibold">What is confirmed about mentoring?</h2><p className="mt-2 text-sm text-ink-600">Program pathways below describe mentoring in an official source. Admission, mentor assignment and individual professors&apos; availability are separate. Public contribution activities may offer tutorials or community discussion, rather than a personal mentor.</p><Link href="/start-research" className="focus-ring mt-3 inline-block rounded-control text-sm font-medium text-brand-700 underline">Not sure which route you need? Start with a research direction</Link></section>
    {!rows.length ? <section className="card mt-6 p-6"><h2 className="text-lg font-semibold">No routes match these filters</h2><p className="mt-2 text-sm text-ink-600">This is a limited collection. No matches here does not mean there are no opportunities for you.</p><Button variant="secondary" className="mt-4" onClick={reset}>Clear opportunity filters</Button><p className="mt-4 text-sm"><a href="https://www.pathwaystoscience.org/K12.aspx" target="_blank" rel="noopener noreferrer" className="focus-ring rounded-control text-brand-700 underline">Explore the Pathways to Science K-12 directory</a></p><p className="mt-2 text-sm"><a href="https://www.pathwaystoscience.org/Undergrads.aspx" target="_blank" rel="noopener noreferrer" className="focus-ring rounded-control text-brand-700 underline">Explore the Pathways to Science undergraduate directory</a></p></section> : <div className="mt-6 grid items-start gap-5 lg:grid-cols-2">{rows.map((row) => {
      const fit = schoolFit(row, level);
      return <article key={row.id} aria-label={row.name} className="card opportunity-card min-w-0 p-5 sm:p-6"><p className="text-xs font-semibold uppercase tracking-wide text-brand-700">{row.kind} / {row.format}</p><h2 className="mt-2 text-xl font-semibold text-ink-950">{row.name}</h2><p className="mt-3 text-sm text-ink-600">{row.description}</p><p className="mt-3 inline-block rounded-pill border border-border px-3 py-1 text-xs font-medium">{now ? opportunityStatus(row, now) : "Checking source-review age..."}</p><p className="mt-2 text-xs text-slate-500">Source reviewed {row.reviewed}. This is not live availability.</p>
        <p className={`mt-4 text-sm font-medium ${fit === "different-level" ? "text-rose-700" : "text-ink"}`}>{fit === "different-level" ? "Your selected school level differs from the published route" : fit === "compatible" ? "School level aligns; remaining requirements need checking" : "Review the participant and account requirements"}</p>
        <details className="mt-4" open={fit === "different-level"}><summary className="focus-ring cursor-pointer rounded-control font-medium text-brand-700">Published requirements</summary><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-600">{row.requirements.map((item) => <li key={item}>{item}</li>)}</ul><p className="mt-3 text-xs text-slate-500">This summary helps you check the source; the provider makes eligibility and selection decisions.</p>{row.eligibilitySource ? <a href={row.eligibilitySource} target="_blank" rel="noopener noreferrer" className="focus-ring mt-3 inline-block rounded-control text-sm text-brand-700 underline">Read the detailed eligibility source <span className="sr-only">(opens in a new tab)</span></a> : null}</details>
        <dl className="mt-5 space-y-3 text-sm">{[["Cycle and deadline", `${row.cycle}. ${row.deadlineLabel}`], ["Commitment", row.commitment], ["Location", row.location], ["Funding and costs", row.funding]].map(([label, value]) => <div key={label}><dt className="font-semibold text-ink">{label}</dt><dd className="mt-1 text-ink-600">{value}</dd></div>)}</dl>
        <details className="mt-5 rounded-control border border-border p-3"><summary className="focus-ring cursor-pointer rounded-control text-sm font-medium">Mentoring evidence and limits</summary><p className="mt-3 text-sm text-ink-600">{row.mentoring}</p><p className="mt-2 text-xs text-slate-500">Evidence applies to this route, not to every professor at the institution.</p></details><a href={row.source} target="_blank" rel="noopener noreferrer" className="focus-ring mt-5 inline-block rounded-control font-semibold text-brand-700 underline">Read {row.name}&apos;s official source <span className="sr-only">(opens in a new tab)</span></a>
      </article>;
    })}</div>}
  </Container>;
}

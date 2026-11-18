"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Compass, BookOpen, Lightbulb, Leaf, Bot, Dna, Orbit, Code2, Landmark, Brain, ArrowUpRight } from "lucide-react";
import { RESEARCH_DIRECTIONS } from "@/data/researchDirections";
import { learningBrief, researcherSearchHref, suggestDirections } from "@/lib/researchLearning";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { LearningIntro } from "./LearningIntro";
import { DirectionGuide } from "./DirectionGuide";

const DIRECTION_ICONS = { environment: Leaf, robotics: Bot, health: Dna, space: Orbit, computing: Code2, humanities: Landmark, behavior: Brain };

export function ResearchStarter() {
  const [interest, setInterest] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [goal, setGoal] = useState("explore");
  const [time, setTime] = useState("short");
  const [selected, setSelected] = useState("");
  const [ownQuestion, setOwnQuestion] = useState("");
  const [background, setBackground] = useState("");
  const [support, setSupport] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const briefRef = useRef<HTMLTextAreaElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const suggestions = submitted ? suggestDirections(submitted, RESEARCH_DIRECTIONS) : [];
  const direction = RESEARCH_DIRECTIONS.find((row) => row.id === selected);
  const brief = direction ? learningBrief(direction, ownQuestion, background, support) : "";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!interest.trim()) { setError("Describe an interest, or choose a direction below."); return; }
    setError(""); setSubmitted(interest.trim()); setSelected(""); setNotice("");
    resultsRef.current?.focus();
  }

  function chooseDirection(id: string) {
    setSelected(id);
    setNotice((ownQuestion.trim() || background.trim() || support.trim()) ? "Your notes are retained. Review them for this direction before copying." : "");
  }

  async function copy() {
    try { await navigator.clipboard.writeText(brief); setNotice("Starting notes copied."); }
    catch { const details = briefRef.current?.closest("details"); if (details) details.open = true; briefRef.current?.focus(); briefRef.current?.select(); setNotice("Clipboard access was blocked. Your notes are selected; copy them manually."); }
  }

  return <Container className="[overflow-wrap:anywhere] py-8 sm:py-12">
    <LearningIntro kind="starter" eyebrow="Start with curiosity" title="Find your first research step">Understand a direction, explore a real pathway, and try a small learning activity. No resume or sign-in needed.</LearningIntro>
    <form onSubmit={submit} className="card mt-6 space-y-4 p-5 sm:p-6" aria-label="Research starter">
      <div><label htmlFor="starter-interest" className="block font-medium text-ink">What are you curious about?</label><textarea id="starter-interest" value={interest} onChange={(event) => setInterest(event.target.value)} maxLength={300} rows={3} placeholder="For example: How can sensors help us understand local flooding?" aria-describedby="starter-help starter-error" className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3 text-ink" /><p id="starter-help" className="mt-1 text-xs text-slate-500">{interest.length}/300 characters. You can also choose a direction without describing yourself.</p></div>
      <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="starter-goal" className="block text-sm font-medium">Your goal</label><select id="starter-goal" value={goal} onChange={(e) => setGoal(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3"><option value="explore">Explore a subject</option><option value="project">Develop my own project question</option><option value="mentor">Find a mentored experience</option></select></div><div><label htmlFor="starter-time" className="block text-sm font-medium">Time you can set aside</label><select id="starter-time" value={time} onChange={(e) => setTime(e.target.value)} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3"><option value="short">A few hours to start</option><option value="regular">Regular time each week</option><option value="summer">A summer commitment</option></select></div></div>
      <p id="starter-error" role={error ? "alert" : undefined} className="text-sm text-rose-700">{error}</p><Button type="submit"><Compass className="h-4 w-4" aria-hidden="true" />Explore directions</Button>
    </form>
    <div ref={resultsRef} tabIndex={-1} className="mt-8 focus:outline-none" aria-live="polite">
      <h2 className="text-xl font-semibold text-ink-950">{submitted ? "Choose a direction to explore" : "Or start with a direction"}</h2>
      {submitted ? <p className="mt-2 text-sm text-slate-500">{suggestions.length ? "These starting directions share terms with your interest. Choose what feels relevant; they are not an assessment of your ability." : "We do not have a confident direction for that description. Choose a guide below, or search the directory in your own words."}</p> : null}
      {submitted ? <Link href={researcherSearchHref(submitted)} className="focus-ring mt-3 inline-block rounded-control text-sm text-brand-700 underline">Search the directory for this interest</Link> : null}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{(suggestions.length ? suggestions : RESEARCH_DIRECTIONS).map((row) => <button key={row.id} type="button" aria-pressed={selected === row.id} onClick={() => chooseDirection(row.id)} className={`focus-ring direction-choice ${selected === row.id ? "direction-choice-selected" : ""}`}><span className="mb-5 flex items-center justify-between gap-3"><span className="direction-choice-icon" aria-hidden="true">{(() => { const Icon = DIRECTION_ICONS[row.id as keyof typeof DIRECTION_ICONS] || Compass; return <Icon className="h-5 w-5" />; })()}</span><ArrowUpRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" /></span><span className="block font-semibold text-ink">{row.title}</span><span className="mt-2 block text-sm leading-relaxed text-ink-600">{row.question}</span></button>)}</div>
      {suggestions.length ? <details className="mt-4"><summary className="focus-ring cursor-pointer rounded-control text-sm text-brand-700">Explore other directions</summary><div className="mt-3 flex flex-wrap gap-2">{RESEARCH_DIRECTIONS.filter((row) => !suggestions.includes(row)).map((row) => <Button key={row.id} variant="secondary" onClick={() => chooseDirection(row.id)}>{row.title}</Button>)}</div></details> : null}
    </div>
    {direction ? <div className="mt-8 space-y-6">
      <section className="panel-aqua p-5 sm:p-6" aria-labelledby="next-step-title"><h2 id="next-step-title" className="text-xl font-semibold text-ink">Your next step</h2><p className="mt-3 text-sm leading-relaxed text-ink-600">{goal === "mentor" ? "Review a source-confirmed mentoring pathway and its requirements, then explore relevant researchers. A research match does not confirm a place or mentoring availability." : goal === "project" ? "Explore the learning activity, then write a question in your own words and discuss its feasibility with a teacher or mentor." : "Read the field guide, try a suitable introductory activity, and notice which part makes you want to learn more."}</p><p className="mt-2 text-sm text-ink-600">{time === "short" ? "Start with the resource's introduction or tutorial. Many placements require much more time than a few hours." : time === "summer" ? "Check the program's dates, full-time commitment, housing and application cycle before choosing a placement." : "Use one small learning step to assess the time and background you would need before committing."}</p><Link href={`/opportunities?direction=${direction.id}${goal === "mentor" ? "&mentoring=1" : ""}`} className="focus-ring mt-4 inline-block rounded-control font-semibold text-brand-700 underline">{goal === "mentor" ? "Check mentoring pathways" : "Explore programs and public activities"}</Link></section>
      <section className="card p-5 sm:p-6" aria-labelledby="understand-area"><h2 id="understand-area" className="mb-5 flex items-center gap-2 text-xl font-semibold"><BookOpen className="h-5 w-5" aria-hidden="true" />Understand {direction.title.toLowerCase()}</h2><DirectionGuide direction={direction} /></section>
      <section className="card p-5 sm:p-6" aria-labelledby="small-project"><h2 id="small-project" className="flex items-center gap-2 text-xl font-semibold"><Lightbulb className="h-5 w-5" aria-hidden="true" />A small first activity</h2><h3 className="mt-4 font-semibold">{direction.activity}</h3><p className="mt-2 text-sm text-slate-500">A learning activity, not a claim of an original finding or a finished research plan. Follow the provider&apos;s instructions and involve a teacher when appropriate.</p><ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-ink-600">{direction.steps.map((step) => <li key={step}>{step}</li>)}</ol><p className="mt-4 text-sm"><strong>What you need:</strong> {direction.materials}</p><p className="mt-3 text-sm"><strong>Think about:</strong> {direction.reflection}</p>
        <div className="mt-5 grid gap-4"><label className="text-sm font-medium" htmlFor="own-question">My question, in my own words<textarea id="own-question" rows={2} maxLength={500} value={ownQuestion} onChange={(e) => { setOwnQuestion(e.target.value); setNotice(""); }} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3 font-normal" /></label><label className="text-sm font-medium" htmlFor="own-background">What I already know<textarea id="own-background" rows={2} maxLength={500} value={background} onChange={(e) => { setBackground(e.target.value); setNotice(""); }} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3 font-normal" /></label><label className="text-sm font-medium" htmlFor="own-support">What I need help with<textarea id="own-support" rows={2} maxLength={500} value={support} onChange={(e) => { setSupport(e.target.value); setNotice(""); }} className="focus-ring mt-2 w-full rounded-control border border-border bg-surface p-3 font-normal" /></label></div>
        <details className="mt-5"><summary className="focus-ring cursor-pointer rounded-control font-medium">Review my starting notes</summary><label htmlFor="starting-brief" className="sr-only">Starting notes</label><textarea ref={briefRef} id="starting-brief" readOnly value={brief} rows={12} className="focus-ring mt-3 w-full rounded-control border border-border bg-surface p-3 text-sm" /></details><div className="mt-4 flex flex-wrap gap-3"><Button onClick={() => void copy()} disabled={!ownQuestion.trim()}>Copy my starting notes</Button><Button variant="secondary" onClick={() => { setOwnQuestion(""); setBackground(""); setSupport(""); setNotice("Starting notes cleared."); }}>Clear starting notes</Button></div><p role="status" className="mt-2 text-sm text-brand-700">{notice}</p><p className="mt-3 text-xs text-slate-500">Notes stay in this page and disappear on refresh. Copy them before leaving. These inputs are not sent to AI or saved to your account.</p>
      </section>
    </div> : null}
  </Container>;
}

import type { ResearchDirection } from "../data/researchDirections.ts";
import type { ResearchOpportunity } from "../data/researchOpportunities.ts";

export function matchesConcept(text: string, concept: string): boolean {
  const words = concept.normalize("NFKC").toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${words}(?:s|ing)?\\b`, "i").test(text.normalize("NFKC"));
}

export function suggestDirections(text: string, directions: ResearchDirection[]): ResearchDirection[] {
  if (!text.trim()) return [];
  return directions.map((direction) => ({ direction, score: direction.keywords.filter((word) => matchesConcept(text, word)).length }))
    .filter((row) => row.score > 0).sort((a, b) => b.score - a.score).slice(0, 3).map((row) => row.direction);
}

export function sourceIsFresh(reviewed: string, now: Date): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reviewed)) return false;
  const stamp = Date.parse(reviewed + "T00:00:00Z");
  const today = Date.parse(now.toISOString().slice(0, 10) + "T00:00:00Z");
  return Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 10) === reviewed && stamp <= today && today - stamp < 30 * 86400000;
}

export function opportunityStatus(opportunity: ResearchOpportunity, now: Date): string {
  if (opportunity.deadline && Date.parse(opportunity.deadline) <= now.getTime()) return "Published deadline passed";
  if (!sourceIsFresh(opportunity.reviewed, now)) return "Source review overdue";
  if (opportunity.accepting === true) return "Applications open when checked";
  if (opportunity.accepting === false) return "Applications closed when checked";
  return "Check current participation";
}

export function schoolFit(opportunity: ResearchOpportunity, level: string): "check" | "compatible" | "different-level" {
  if (!level || !opportunity.schoolLevels.length) return "check";
  return opportunity.schoolLevels.includes(level) ? "compatible" : "different-level";
}

export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function researcherSearchHref(query: string): string {
  return "/discover?" + new URLSearchParams({ q: query.trim().slice(0, 300) }).toString();
}

export function learningBrief(direction: ResearchDirection, ownQuestion: string, background: string, support: string): string {
  return ["My research starting notes", `Direction: ${direction.title}`, `My question: ${ownQuestion.trim() || "Still exploring"}`, `What I already know: ${background.trim() || "To discuss"}`, `What I need help with: ${support.trim() || "To discuss"}`, `Learning resource: ${direction.source.url}`, "These are my starting notes, not a completed research plan or a claim of an original finding."].join("\n\n");
}

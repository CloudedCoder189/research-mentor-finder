import type { Metadata } from "next";
import { OpportunityFinder } from "@/components/learning/OpportunityFinder";
import { RESEARCH_DIRECTIONS } from "@/data/researchDirections";
export const metadata: Metadata = { title: "Research opportunities", description: "Source-checked research programs, mentoring pathways and public contribution activities." };
export default async function Page({ searchParams }: { searchParams: Promise<{ direction?: string | string[]; mentoring?: string | string[] }> }) {
  const params = await searchParams;
  const direction = typeof params.direction === "string" && RESEARCH_DIRECTIONS.some((row) => row.id === params.direction) ? params.direction : "";
  return <OpportunityFinder key={`${direction}:${params.mentoring === "1"}`} initialDirection={direction} initialMentoring={params.mentoring === "1"} initialNow={new Date().toISOString()} />;
}

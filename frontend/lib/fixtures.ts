import { RESEARCHERS } from "@/data/researchers";
import { DEFAULT_SAVED, outreachFor } from "@/data/outreach";
import { DEFAULT_STUDENT_PROFILE } from "@/data/studentProfile";
import type { OutreachEntry, OutreachStatus, Researcher, StudentProfile } from "@/types";

export function getAllResearchers(): Researcher[] {
  return RESEARCHERS;
}

export function getResearcherById(id: string): Researcher | undefined {
  return RESEARCHERS.find((r) => r.id === id);
}

export function getOutreachStatus(researcherId: string): OutreachStatus {
  return outreachFor(researcherId)?.status ?? "Not contacted";
}

export function getOutreachForResearcher(researcherId: string): OutreachEntry | undefined {
  return outreachFor(researcherId);
}

export function isSavedByDefault(researcherId: string): boolean {
  return DEFAULT_SAVED.includes(researcherId);
}

export function getStudentProfile(): StudentProfile {
  return DEFAULT_STUDENT_PROFILE;
}

export function getDefaultSavedIds(): string[] {
  return DEFAULT_SAVED;
}
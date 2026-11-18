import type { EducationLevel, Researcher, StudentProfile } from "@/types";

export const DEFAULT_EDUCATION_LEVEL: EducationLevel = "unspecified";

const EDUCATION_LEVEL_PHRASES: Partial<Record<EducationLevel, string>> = {
  high_school: "high school student",
  college: "college student",
  university: "university student",
  graduate: "graduate student",
};

export interface OutreachDraft {
  subject: string;
  body: string;
}

function lastName(name: string): string {
  const parts = name.replace(/^Dr\.\s*/i, "").trim().split(/\s+/);
  return parts[parts.length - 1] ?? name;
}

export function educationLevelPhrase(level: EducationLevel | undefined): string {
  return EDUCATION_LEVEL_PHRASES[level ?? DEFAULT_EDUCATION_LEVEL] ?? "student";
}

export function buildOutreachDraft(researcher: Researcher, profile: StudentProfile): OutreachDraft {
  // Prefer a shared, explicitly recorded topic. Do not infer a paper or opening.
  const normalized = (value: string) => value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const interestsForMatch = profile.interests.map(normalized).filter(Boolean);
  const topic = researcher.topics.find(value => interestsForMatch.includes(normalized(value)))
    ?? researcher.topics.find(value => interestsForMatch.some(interest => {
      const candidate = ` ${normalized(value)} `;
      return candidate.includes(` ${interest} `) || ` ${interest} `.includes(candidate);
    }))
    ?? researcher.field;
  const subject = topic ? `Research interest in ${topic}` : "Question about your research";
  const phrase = educationLevelPhrase(profile.education_level);
  const interests = profile.interests.slice(0, 2).join(", ");
  const opening = interests
    ? `I'm a ${phrase} interested in ${interests}, and I came across your work on ${topic || "your research area"} at ${researcher.university}.`
    : `I'm a ${phrase}, and I came across your work on ${topic || "your research area"} at ${researcher.university}.`;

  const facts: string[] = [];
  if (profile.skills.length > 0) {
    facts.push(`I have experience with ${profile.skills.slice(0, 3).join(", ")}.`);
  }
  if (profile.experience.length > 0) {
    facts.push(`My projects and experience include:\n${profile.experience.slice(0, 2).map(item => `- ${item.trim()}`).join("\n")}`);
  }
  if (profile.coursework.length > 0) {
    facts.push(`My coursework includes ${profile.coursework.slice(0, 3).join(", ")}.`);
  }
  const factBlock = facts.length > 0 ? `\n\n${facts.join("\n")}` : "";

  const body =
    `Dear Dr. ${lastName(researcher.name)},\n\n` +
    `${opening}${factBlock}\n\n` +
    `I would love to know whether you're open to mentoring students this year, and what a good first step would be.\n\n` +
    `Thank you for your time.\n\n` +
    `Best regards,\n[Your name]`;

  return { subject, body };
}

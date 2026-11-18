/* Regression tests for grounded outreach draft generation.
 * Runnable with the installed Node (no test framework):
 *   npm run test:draft
 */
import assert from "node:assert/strict";
import { buildOutreachDraft } from "../lib/outreachDraft.ts";
import type { EducationLevel, Researcher, StudentProfile } from "../types/index.ts";

const researcher: Researcher = {
  id: "ada-lovelace",
  name: "Dr. Ada Lovelace",
  university: "Stanford University",
  department: "Computer Science",
  title: "Professor",
  city: "Stanford",
  state: "CA",
  field: "Machine Learning",
  email: "ada@stanford.edu",
  websiteUrl: null,
  websiteStatus: "Verified",
  profileUrl: null,
  topics: ["Reinforcement Learning"],
  researchOverview: "",
  researchInterests: "",
  verificationStatus: "Verified",
  verificationNote: "",
  opportunityLevel: "",
  source: "fixture",
  sourceUrl: "",
};

function profile(overrides: Partial<StudentProfile> = {}): StudentProfile {
  return {
    interests: [],
    interestText: "",
    skills: [],
    experience: [],
    coursework: [],
    education_level: "high_school",
    preferences: {
      locations: [],
      universityTypes: [],
      supportLevel: "No preference",
      remoteOk: false,
    },
    resume: { fileName: null },
    completed: false,
    ...overrides,
  };
}

function combined(draft: { subject: string; body: string }): string {
  return `${draft.subject}\n${draft.body}`;
}

// 1. Default profile generates "high school student".
{
  const draft = buildOutreachDraft(researcher, profile());
  assert.match(draft.body, /high school student/);
  assert.equal(draft.subject, "Research interest in Machine Learning");
}

// Missing education must not invent an education level.
{
  const legacyProfile = { ...profile(), education_level: undefined as unknown as EducationLevel };
  const draft = buildOutreachDraft(researcher, legacyProfile);
  assert.match(draft.body, /I'm a student/);
  assert.doesNotMatch(draft.body, /high school/);
}

// 2. Generated draft does not contain "undergraduate".
{
  const draft = buildOutreachDraft(researcher, profile({ interests: ["Machine Learning"] }));
  assert.ok(!/undergraduate/i.test(combined(draft)));
}

// 3. Generated draft does not claim other invented statuses.
{
  const draft = buildOutreachDraft(researcher, profile({ interests: ["Machine Learning"] }));
  assert.ok(!/college student/i.test(combined(draft)));
  assert.ok(!/university student/i.test(combined(draft)));
  assert.ok(!/graduate student/i.test(combined(draft)));
  assert.ok(!/research assistant/i.test(combined(draft)));
}

// 4. Skills and projects are mentioned only when supplied.
{
  const empty = buildOutreachDraft(researcher, profile({ interests: ["Machine Learning"] }));
  assert.ok(!/Python/i.test(combined(empty)));
  assert.ok(!/experience with/i.test(combined(empty)));
  assert.ok(!/Built a model/i.test(combined(empty)));

  const filled = buildOutreachDraft(
    researcher,
    profile({
      interests: ["Machine Learning"],
      skills: ["Python"],
      experience: ["Built a model"],
    }),
  );
  assert.match(combined(filled), /I have experience with Python\./);
  assert.match(combined(filled), /Built a model/);
}

// 5. A sparse profile still produces a truthful email.
{
  const draft = buildOutreachDraft(researcher, profile());
  assert.match(draft.body, /high school student/);
  assert.match(draft.body, /Machine Learning/);
  assert.match(draft.body, /Stanford University/);
  assert.ok(!/interested in/i.test(draft.body));
  assert.ok(!/degree|research experience|internship|publication|award/i.test(draft.body));
}

// 6. Professor and research facts stay grounded in actual professor data.
{
  const draft = buildOutreachDraft(researcher, profile({ interests: ["Machine Learning"] }));
  assert.match(draft.body, /Dr\. Lovelace/);
  assert.match(draft.body, /Machine Learning/);
  assert.match(draft.body, /Stanford University/);
  assert.ok(!/Quantum Biology/i.test(combined(draft)));
  assert.ok(!/undergraduate|college student|university student|graduate student|research assistant/i.test(combined(draft)));
}

// Full sentences from resume experience keep their punctuation and boundaries.
{
  const draft = buildOutreachDraft(researcher, profile({ experience: ["Built an Arduino sensor.", "Compared indoor readings!"] }));
  assert.match(draft.body, /- Built an Arduino sensor\.\n- Compared indoor readings!/);
  assert.ok(!draft.body.includes("sensor.."));
}

console.log("test:draft: grounded outreach regression checks passed.");

// College, neutral profiles, and shared topics must survive generation.
{
  const person = { ...researcher, topics: ["Machine Learning", "Robotics"] };
  const draft = buildOutreachDraft(person, profile({ education_level: "college", interests: ["Robotics"] }));
  assert.match(draft.body, /college student/);
  assert.doesNotMatch(draft.body, /high school/);
  assert.equal(draft.subject, "Research interest in Robotics");
  const neutral = buildOutreachDraft(person, profile({ education_level: "unspecified" }));
  assert.match(neutral.body, /I'm a student/);
  assert.doesNotMatch(neutral.body, /high school|college student/);
  const noTopic = buildOutreachDraft({ ...person, topics: [], field: "" }, profile());
  assert.equal(noTopic.subject, "Question about your research");
  assert.doesNotMatch(noTopic.body, /undefined/);
}
console.log("Education and shared-topic regressions passed.");

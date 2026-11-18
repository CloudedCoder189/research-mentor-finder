// DEMONSTRATION DATA ONLY
// The researchers, outreach histories, notes, and drafts below
// are fictional examples for showcasing application features.
// They do not represent actual student outreach activity.

import type { OutreachEntry } from "@/types";

export const OUTREACH: OutreachEntry[] = [
  {
    researcherId: "maria-chen",
    status: "Drafted",
    notes: "Loves the accessibility work. Mention her NAACL paper on collaborative design.",
    followUpDate: null,
    emailSentAt: null,
    saved: true,
    draft: {
      subject: "Undergraduate research interest in accessible, human-centered AI",
      body: "Dear Dr. Chen,\n\nI'm an undergraduate at Western Washington University studying computer science, and I've been following your work on AI-assisted design tools and accessibility. I'm especially interested in how machine learning can make interfaces more usable for everyone.\n\nI would love the chance to learn more about your current projects and whether there might be an opportunity to contribute, even in a small way.\n\nThank you for your time.\n\nBest regards,\n[Your name]",
    },
  },
  {
    researcherId: "david-park",
    status: "Sent",
    notes: "Sent Monday. Follow up in ~1 week.",
    followUpDate: "2026-09-21",
    emailSentAt: "2026-09-14",
    saved: true,
    draft: {
      subject: "Inquiry about NLP research opportunities",
      body: "Dear Dr. Park,\n\nI'm a student interested in natural language processing...",
    },
  },
  {
    researcherId: "liam-anderson",
    status: "Replied",
    notes: "Replied! Wants to talk in the third week of September.",
    followUpDate: "2026-09-23",
    emailSentAt: "2026-09-10",
    saved: true,
  },
  {
    researcherId: "james-wilson",
    status: "Meeting scheduled",
    notes: "Meeting Oct 2, 2pm PT. Reviewed two of his imaging papers.",
    followUpDate: null,
    emailSentAt: "2026-09-08",
    saved: true,
  },
  {
    researcherId: "emma-davis",
    status: "Follow-up due",
    notes: "No reply to first email yet. Onboarding packet ready if she says yes.",
    followUpDate: "2026-09-16",
    emailSentAt: "2026-09-02",
    saved: true,
  },
  {
    researcherId: "mia-johnson",
    status: "Closed",
    notes: "Connected with her lab via a different program. Not pursuing here.",
    followUpDate: null,
    emailSentAt: "2026-08-20",
    saved: true,
  },
  {
    researcherId: "olivia-white",
    status: "Drafted",
    notes: "Local option in Bellingham — good fallback if moving is hard.",
    followUpDate: null,
    emailSentAt: null,
    saved: true,
    draft: {
      subject: "Interest in computing education research",
      body: "Dear Dr. White,\n\nI'm a student in Bellingham interested in computing education...",
    },
  },
  {
    researcherId: "ethan-nguyen",
    status: "Sent",
    notes: "Sent. Also reached the department's undergrad coordinator.",
    followUpDate: "2026-09-25",
    emailSentAt: "2026-09-12",
    saved: true,
  },
  {
    researcherId: "ryan-thomas",
    status: "Follow-up due",
    notes: "Previous draft followed up. Replied that they may open spots mid-semester.",
    followUpDate: "2026-09-18",
    emailSentAt: "2026-09-05",
    saved: true,
  },
];

export const DEFAULT_SAVED: string[] = OUTREACH.filter((entry) => entry.saved).map(
  (entry) => entry.researcherId,
);

export function outreachFor(researcherId: string): OutreachEntry | undefined {
  return OUTREACH.find((entry) => entry.researcherId === researcherId);
}
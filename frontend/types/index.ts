export type VerificationStatus = "Verified" | "Review" | "Failed" | "Not checked";

export type WebsiteStatus = "Verified" | "Review" | "Broken" | "Not checked";

export type OutreachStatus =
  | "Not contacted"
  | "Drafted"
  | "Sent"
  | "Replied"
  | "Meeting scheduled"
  | "Follow-up due"
  | "Closed";

export type MatchLabel =
  | "Strong match"
  | "Good match"
  | "Possible match"
  | "Limited match"
  | "Strong research match"
  | "Good research match"
  | "Potential match";

export type EducationLevel = "unspecified" | "high_school" | "college" | "university" | "graduate";

export interface Researcher {
  affiliationFields?: string[];
  affiliationDisciplines?: string[];
  id: string;
  name: string;
  university: string;
  department: string;
  title: string;
  city: string;
  state: string;
  field: string;
  /** Broad academic area for `field`, from the API taxonomy. Absent on
   *  static seed fixtures, which only carry a field label. */
  discipline?: string;
  email: string;
  websiteUrl: string | null;
  websiteStatus: WebsiteStatus;
  profileUrl: string | null;
  topics: string[];
  researchOverview: string;
  researchInterests: string;
  verificationStatus: VerificationStatus;
  verificationNote: string;
  opportunityLevel: string;
  source: string;
  sourceUrl: string;
}

export interface OutreachEntry {
  researcherId: string;
  status: OutreachStatus;
  notes: string;
  followUpDate: string | null;
  emailSentAt: string | null;
  saved: boolean;
  draft?: {
    subject: string;
    body: string;
  };
}

export interface SavedOutreachState {
  isFavorite: boolean;
  status: OutreachStatus;
  notes: string;
  emailSentAt: string | null;
  followUpDate: string | null;
  followUpDue: boolean;
  emailTo: string;
  emailSubject: string;
  emailBody: string;
  gmailSentAt: string | null;
  gmailRepliedAt: string | null;
  gmailReplyCount: number;
  gmailLastCheckedAt: string | null;
  updatedAt: string;
}

export interface SavedResult {
  researcher: Researcher;
  outreach: SavedOutreachState;
}

export interface ResearcherMatch {
  label: MatchLabel;
  score: number;
  reasons: string[];
  signals?: { source: string; label: string; detail: string; topic?: string }[];
  aiExplanation?: {
    source: string;
    model: string;
    reasons: string[];
    status: string;
  };
}

export interface RecommendationSignal {
  source: "interests" | "skills" | "projects" | "coursework" | "location";
  label: string;
  detail: string;
}

export interface StudentProfile {
  interests: string[];
  interestText: string;
  skills: string[];
  experience: string[];
  coursework: string[];
  education_level: EducationLevel;
  preferences: {
    locations: string[];
    universityTypes: string[];
    supportLevel: string;
    remoteOk: boolean;
  };
  resume: {
    fileName: string | null;
  };
  completed: boolean;
}

export interface ResearchTopic {
  label: string;
  area: string;
}

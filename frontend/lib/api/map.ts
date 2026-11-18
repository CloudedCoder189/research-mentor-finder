import type {
  ResearcherProfileDto,
  MatchDto,
  OutreachResultDto,
  ProfileInputDto,
  RecommendationMatchDto,
  ResearcherDto,
} from "@/lib/api/types";
import type { MatchLabel, Researcher, ResearcherMatch, SavedResult, StudentProfile, WebsiteStatus } from "@/types";

function matchLabel(strength: string): MatchLabel {
  if (strength === "Strong match") return "Strong match";
  if (strength === "Related match") return "Good match";
  return "Possible match";
}

export function toResearcher(dto: ResearcherDto): Researcher {
  return {
    id: String(dto.id),
    name: dto.name,
    university: dto.university,
    department: dto.department,
    title: dto.title,
    city: dto.city,
    state: dto.state,
    field: dto.field,
    discipline: dto.discipline,
    affiliationFields: dto.affiliation_fields ?? [],
    affiliationDisciplines: dto.affiliation_disciplines ?? [],
    email: /^\S+@\S+\.\S+$/.test(dto.email.trim()) ? dto.email.trim() : "",
    websiteUrl: null,
    websiteStatus: "Not checked",
    profileUrl: null,
    topics: dto.topics,
    researchOverview: dto.ai_summary,
    researchInterests: dto.research_interests,
    verificationStatus: dto.verification_status,
    verificationNote: "",
    opportunityLevel: dto.opportunity_level,
    source: "",
    sourceUrl: dto.data_source_url,
  };
}

export function toProfileResearcher(profile: ResearcherProfileDto): Researcher {
  const base = toResearcher(profile.researcher);
  return {
    ...base,
    websiteUrl: profile.website_url || null,
    websiteStatus: profile.website_status_label as WebsiteStatus,
    profileUrl: profile.profile_url || null,
    verificationNote: profile.verification_issues || "",
    opportunityLevel: profile.researcher.opportunity_level,
    source: profile.source_type,
    sourceUrl: profile.researcher.data_source_url,
  };
}

export function toMatch(dto: MatchDto | null): ResearcherMatch | undefined {
  if (!dto) return undefined;
  return {
    label: matchLabel(dto.strength),
    score: dto.score,
    reasons: [dto.reason],
  };
}

export function toRecommendationMatch(
  dto: RecommendationMatchDto,
): ResearcherMatch {
  return {
    label: dto.label,
    score: dto.research_fit_score,
    reasons: dto.reasons,
    signals: dto.signals,
    aiExplanation: dto.ai_explanation
      ? {
          source: dto.ai_explanation.source,
          model: dto.ai_explanation.model,
          reasons: dto.ai_explanation.reasons,
          status: dto.ai_explanation.status,
        }
      : undefined,
  };
}

export function toRecommendationResult(
  result: { researcher: ResearcherDto; match: RecommendationMatchDto },
): { researcher: Researcher; match: ResearcherMatch } {
  return {
    researcher: toResearcher(result.researcher),
    match: toRecommendationMatch(result.match),
  };
}

export function toProfileInput(profile: StudentProfile): ProfileInputDto {
  return {
    interests: profile.interests,
    interest_text: profile.interestText,
    skills: profile.skills,
    experience: profile.experience,
    coursework: profile.coursework,
    preferences: {
      locations: profile.preferences.locations,
      remote_ok: profile.preferences.remoteOk,
    },
  };
}

export function toSavedResult(dto: OutreachResultDto): SavedResult {
  return {
    researcher: toResearcher(dto.researcher),
    outreach: {
      isFavorite: dto.outreach.is_favorite,
      status: dto.outreach.status,
      notes: dto.outreach.notes,
      emailSentAt: dto.outreach.email_sent_at || null,
      followUpDate: dto.outreach.follow_up_date || null,
      followUpDue: dto.outreach.follow_up_due,
      emailTo: dto.outreach.email_to,
      emailSubject: dto.outreach.email_subject,
      emailBody: dto.outreach.email_body,
      gmailSentAt: dto.outreach.gmail_sent_at || null,
      gmailRepliedAt: dto.outreach.gmail_replied_at || null,
      gmailReplyCount: dto.outreach.gmail_reply_count,
      gmailLastCheckedAt: dto.outreach.gmail_last_checked_at || null,
      updatedAt: dto.outreach.updated_at,
    },
  };
}

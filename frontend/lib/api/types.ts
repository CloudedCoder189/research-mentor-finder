import type { MatchLabel, OutreachStatus, VerificationStatus, WebsiteStatus } from "@/types";

export interface ResearcherDto {
  id: number;
  name: string;
  university: string;
  department: string;
  title: string;
  city: string;
  state: string;
  field: string;
  discipline: string;
  affiliation_fields?: string[];
  affiliation_disciplines?: string[];
  topics: string[];
  research_interests: string;
  ai_summary: string;
  email: string;
  verification_status: VerificationStatus;
  opportunity_level: string;
  data_source_url: string;
}

export interface MatchDto {
  score: number;
  keyword_score: number;
  semantic_score: number;
  mode: string;
  reason: string;
  strength: string;
}

export interface SearchResultDto {
  researcher: ResearcherDto;
  match: MatchDto | null;
}

export interface SearchResponseDto {
  query: string;
  mode: string;
  semantic_cached: boolean;
  total: number;
  offset: number;
  limit: number;
  results: SearchResultDto[];
  fallback_message: string;
}

export interface ResearcherProfileDto {
  researcher: ResearcherDto;
  department_category: string;
  website_url: string;
  website_status_label: WebsiteStatus;
  website_status_detail: string;
  website_checked_at: string;
  profile_url: string;
  verification_issues: string;
  verified_at: string;
  last_checked_at: string;
  opportunity_signals: string;
  opportunity_source_url: string;
  source_type: string;
}

export interface OptionsDto {
  universities: string[];
  states: string[];
  fields: string[];
  department_categories: string[];
  verification_statuses: VerificationStatus[];
  opportunity_signals: string[];
  total_researchers: number;
}

export interface SearchParams {
  query: string;
  university?: string;
  state?: string;
  field?: string;
  verification?: string;
  opportunity?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}

export interface RecommendationSignalDto {
  source: string;
  label: string;
  detail: string;
  topic?: string;
}

export interface RecommendationExplanationDto {
  source: string;
  model: string;
  reasons: string[];
  status: string;
}

export interface RecommendationMatchDto {
  label: MatchLabel;
  research_fit_score: number;
  components: Record<string, number>;
  reasons: string[];
  signals: RecommendationSignalDto[];
  ai_explanation?: RecommendationExplanationDto | null;
}

export interface RecommendationResultDto {
  researcher: ResearcherDto;
  match: RecommendationMatchDto;
}

export interface RecommendationResponseDto {
  generated_at: string;
  query: string;
  mode: string;
  semantic_cached: boolean;
  total: number;
  offset: number;
  limit: number;
  results: RecommendationResultDto[];
  fallback_message: string;
}

export interface ProfilePreferencesDto {
  locations: string[];
  remote_ok: boolean;
  university_types?: string[];
  support_level?: string;
}

export interface ProfileInputDto {
  interests: string[];
  interest_text?: string;
  skills?: string[];
  experience?: string[];
  coursework?: string[];
  education_level?: string;
  preferences?: ProfilePreferencesDto;
}

export interface AuthUserDto {
  user_id: string;
  email: string;
  display_name: string;
  avatar_url: string;
}

export interface AuthStatusDto {
  authenticated: boolean;
  user: AuthUserDto | null;
  csrf_token: string | null;
  dev_login_available: boolean;
  local_import_available?: boolean;
}

export interface ImportLocalDto {
  imported_outreach_rows: number;
  imported_gmail_tokens: boolean;
  already_imported: boolean;
}

export interface FullProfilePreferencesDto {
  locations: string[];
  university_types: string[];
  support_level: string;
  remote_ok: boolean;
}

export interface StudentProfileDto {
  interests: string[];
  interest_text: string;
  skills: string[];
  experience: string[];
  coursework: string[];
  education_level: string;
  preferences: FullProfilePreferencesDto;
  completed: boolean;
  updated_at: string;
}

export interface StudentProfileUpdateDto {
  expected_user_id?: string;
  interests: string[];
  interest_text: string;
  skills: string[];
  experience: string[];
  coursework: string[];
  education_level: string;
  preferences: FullProfilePreferencesDto;
  completed: boolean;
}

export interface RecommendationFiltersDto {
  university?: string;
  state?: string;
  field?: string;
  verification?: string;
  opportunity?: string;
}

export interface OutreachStateDto {
  is_favorite: boolean;
  status: OutreachStatus;
  notes: string;
  email_sent_at: string;
  follow_up_date: string;
  email_to: string;
  email_subject: string;
  email_body: string;
  gmail_draft_id: string;
  gmail_thread_id: string;
  gmail_account_email: string;
  gmail_draft_created_at: string;
  gmail_sent_at: string;
  gmail_replied_at: string;
  gmail_reply_count: number;
  gmail_last_checked_at: string;
  updated_at: string;
  follow_up_due: boolean;
}

export interface GmailStatusDto {
  connected: boolean;
  available?: boolean;
  account_email: string;
  scope: string;
  expires_in_seconds: number | null;
  draft_url: string;
}

export interface GmailConnectDto {
  auth_url: string;
}

export interface GmailDisconnectDto {
  disconnected: boolean;
  revocation: "revoked" | "unconfirmed" | "not_connected";
}

export interface GmailDraftInputDto {
  to?: string | null;
  subject?: string | null;
  body?: string | null;
  notes?: string | null;
}

export interface GmailDraftResultDto {
  gmail_draft_id: string;
  gmail_thread_id: string;
  gmail_account_email: string;
  gmail_draft_created_at: string;
  outreach: OutreachResultDto;
}

export interface OutreachResultDto {
  researcher: ResearcherDto;
  outreach: OutreachStateDto;
}

export interface SavedListDto {
  total: number;
  results: OutreachResultDto[];
}

export interface OutreachListDto {
  total: number;
  results: OutreachResultDto[];
}

export interface OutreachUpdateDto {
  expected_user_id?: string;
  outreach_status?: OutreachStatus | null;
  notes?: string | null;
  email_sent_at?: string | null;
  follow_up_date?: string | null;
  email_to?: string | null;
  email_subject?: string | null;
  email_body?: string | null;
}

export interface SavedMutationDto {
  professor_id: number;
  saved: boolean;
}

export interface GmailSyncResultDto {
  professor_id: number;
  linked: boolean;
  sent: boolean;
  replied: boolean;
  preserved: boolean;
  not_sent_yet: boolean;
  checked_at: string;
  message: string;
  outreach: OutreachResultDto | null;
}

export interface GmailSyncAllResultDto {
  checked: number;
  updated: number;
  errors: string[];
  results: GmailSyncResultDto[];
}

export interface FollowUpDraftResultDto {
  professor_id: number;
  message: string;
  outreach: OutreachResultDto;
}

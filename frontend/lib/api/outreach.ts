import { apiFetch } from "@/lib/api/client";
import type {
  FollowUpDraftResultDto,
  GmailSyncAllResultDto,
  GmailSyncResultDto,
  OutreachListDto,
  OutreachResultDto,
  OutreachUpdateDto,
  SavedListDto,
  SavedMutationDto,
} from "@/lib/api/types";

export function getSavedResearchers(signal?: AbortSignal): Promise<SavedListDto> {
  return apiFetch<SavedListDto>("/api/saved", { signal });
}

export function saveResearcher(professorId: number): Promise<SavedMutationDto> {
  return apiFetch<SavedMutationDto>(`/api/saved/${professorId}`, {
    method: "POST",
  });
}

export function unsaveResearcher(professorId: number): Promise<SavedMutationDto> {
  return apiFetch<SavedMutationDto>(`/api/saved/${professorId}`, {
    method: "DELETE",
  });
}

export function getOutreachRows(signal?: AbortSignal): Promise<OutreachListDto> {
  return apiFetch<OutreachListDto>("/api/outreach", { signal });
}

export function getOutreachFor(professorId: number): Promise<OutreachResultDto> {
  return apiFetch<OutreachResultDto>(`/api/outreach/${professorId}`);
}

export function updateOutreach(
  professorId: number,
  update: OutreachUpdateDto,
): Promise<OutreachResultDto> {
  return apiFetch<OutreachResultDto>(`/api/outreach/${professorId}`, {
    method: "PATCH",
    body: update,
  });
}

export function toNumericId(professorId: string | number): number {
  const value = typeof professorId === "number" ? professorId : Number(professorId);
  return Number.isInteger(value) && value > 0 ? value : 0;
}

export function gmailSyncFor(professorId: number): Promise<GmailSyncResultDto> {
  return apiFetch<GmailSyncResultDto>(`/api/outreach/${professorId}/gmail-sync`, {
    method: "POST",
  });
}

export function gmailSyncAll(): Promise<GmailSyncAllResultDto> {
  return apiFetch<GmailSyncAllResultDto>("/api/outreach/gmail-sync", {
    method: "POST",
  });
}

export function followUpDraft(professorId: number): Promise<FollowUpDraftResultDto> {
  return apiFetch<FollowUpDraftResultDto>(`/api/outreach/${professorId}/follow-up-draft`, {
    method: "POST",
  });
}
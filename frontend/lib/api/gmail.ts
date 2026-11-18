import { apiFetch } from "@/lib/api/client";
import type {
  GmailConnectDto,
  GmailDisconnectDto,
  GmailDraftInputDto,
  GmailDraftResultDto,
  GmailStatusDto,
} from "@/lib/api/types";

export function getGmailStatus(signal?: AbortSignal): Promise<GmailStatusDto> {
  return apiFetch<GmailStatusDto>("/api/gmail/status", { signal });
}

export function beginGmailConnect(): Promise<GmailConnectDto> {
  return apiFetch<GmailConnectDto>("/api/gmail/connect");
}

export function disconnectGmail(): Promise<GmailDisconnectDto> {
  return apiFetch<GmailDisconnectDto>("/api/gmail/disconnect", { method: "POST" });
}

export function createGmailDraft(
  professorId: number,
  payload: GmailDraftInputDto,
): Promise<GmailDraftResultDto> {
  return apiFetch<GmailDraftResultDto>(`/api/outreach/${professorId}/gmail-draft`, {
    method: "POST",
    body: payload,
  });
}

export function updateGmailDraft(
  professorId: number,
  payload: GmailDraftInputDto,
): Promise<GmailDraftResultDto> {
  return apiFetch<GmailDraftResultDto>(`/api/outreach/${professorId}/gmail-draft`, {
    method: "PATCH",
    body: payload,
  });
}
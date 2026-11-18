import { apiFetch } from "@/lib/api/client";
import type {
  ProfileInputDto,
  RecommendationFiltersDto,
  RecommendationResponseDto,
} from "@/lib/api/types";

export function getRecommendations(
  profile: ProfileInputDto,
  filters: RecommendationFiltersDto,
  { limit = 20, offset = 0, signal }: { limit?: number; offset?: number; signal?: AbortSignal } = {},
): Promise<RecommendationResponseDto> {
  return apiFetch<RecommendationResponseDto>("/api/recommendations", {
    method: "POST",
    body: { profile, filters, limit, offset },
    signal,
  });
}

export function explainMatch(
  profile: ProfileInputDto,
  researcherId: string,
  { includeAi = false }: { includeAi?: boolean } = {},
): Promise<RecommendationResponseDto> {
  return apiFetch<RecommendationResponseDto>("/api/recommendations/explain", {
    method: "POST",
    body: { profile, researcher_id: Number(researcherId), include_ai: includeAi },
    timeoutMs: includeAi ? 30000 : 15000,
  });
}

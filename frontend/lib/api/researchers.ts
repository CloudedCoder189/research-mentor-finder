import { apiFetch } from "@/lib/api/client";
import type {
  OptionsDto,
  ResearcherProfileDto,
  SearchParams,
  SearchResponseDto,
} from "@/lib/api/types";

export function getSearchOptions(): Promise<OptionsDto> {
  return apiFetch<OptionsDto>("/api/meta/options");
}

export function searchResearchers(params: SearchParams): Promise<SearchResponseDto> {
  const { query, signal, limit, offset, ...filters } = params;
  return apiFetch<SearchResponseDto>("/api/search", {
    method: "POST",
    body: { query, ...filters, limit: limit ?? 25, offset: offset ?? 0 },
    signal,
  });
}

export function getResearcherProfile(id: string): Promise<ResearcherProfileDto> {
  return apiFetch<ResearcherProfileDto>(`/api/researchers/${encodeURIComponent(id)}`);
}
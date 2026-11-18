import type { Researcher } from "@/types";

/**
 * Client-side mirror of the API's field filter semantics.
 *
 * The API filters broad categories by discipline
 * (`services/ui_helpers.py`: `field_filter_matches`), because the field menus
 * offer broad categories such as "Computing" while individual records carry a
 * specific department-derived field such as "Computer Science". Saved filters
 * its already-loaded rows in the browser, so it has to apply the same rule or
 * the two pages disagree about which records a category includes.
 *
 * Keep in sync with `BROAD_FIELD_CATEGORIES` / `field_filter_matches` in
 * `services/ui_helpers.py`.
 */
export const BROAD_FIELD_CATEGORIES: ReadonlySet<string> = new Set([
  "Computing",
  "Engineering",
  "Mathematics & Computing",
  "Engineering & Computing",
]);

export function fieldFilterMatches(researcher: Researcher, selected: string): boolean {
  if (researcher.field === selected) return true;
  if (!BROAD_FIELD_CATEGORIES.has(selected)) return (researcher.affiliationFields ?? []).includes(selected);
  return (researcher.discipline ?? "") === selected || (researcher.affiliationDisciplines ?? []).includes(selected);
}

/** Mirror services/ui_helpers.py outreach_filter_matches. */
export function opportunityFilterMatches(level: string, selected: string): boolean {
  if (selected === "Moderate or strong") return level === "Moderate" || level === "Strong";
  if (selected === "Strong only") return level === "Strong";
  return true;
}

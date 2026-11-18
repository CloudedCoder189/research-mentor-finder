"use client";

import { ChevronDown, Filter, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Select } from "@/components/ui/Input";
import {
  FIELD_OPTIONS,
  OPPORTUNITY_OPTIONS,
  STATE_OPTIONS,
  UNIVERSITY_OPTIONS,
  VERIFICATION_OPTIONS,
} from "@/data/options";

export interface FilterValues {
  university: string;
  field: string;
  state: string;
  verification: string;
  opportunity: string;
}

export interface FilterBarOptions {
  universities: string[];
  fields: string[];
  states: string[];
  verificationStatuses: string[];
  opportunitySignals: string[];
}

const FALLBACK_OPTIONS: FilterBarOptions = {
  universities: UNIVERSITY_OPTIONS,
  fields: FIELD_OPTIONS,
  states: STATE_OPTIONS,
  verificationStatuses: [...VERIFICATION_OPTIONS],
  opportunitySignals: [...OPPORTUNITY_OPTIONS],
};

export const EMPTY_FILTERS: FilterValues = {
  university: "Any university",
  field: "Any field",
  state: "Any state",
  verification: "Any status",
  opportunity: "Any level",
};

export function FilterBar({
  values,
  onChange,
  options,
}: {
  values: FilterValues;
  onChange: (next: FilterValues) => void;
  options?: Partial<FilterBarOptions>;
}) {
  const [expanded, setExpanded] = useState(
    () => values.verification !== EMPTY_FILTERS.verification || values.opportunity !== EMPTY_FILTERS.opportunity,
  );
  const merged = { ...FALLBACK_OPTIONS, ...options };
  const activeFilters = [
    { key: "university", label: "University" },
    { key: "field", label: "Field" },
    { key: "state", label: "State" },
    { key: "verification", label: "Verification" },
    { key: "opportunity", label: "Opportunity signals" },
  ].filter(({ key }) => values[key as keyof FilterValues] !== EMPTY_FILTERS[key as keyof FilterValues]);
  const touched = Object.keys(values).some(
    (key) => values[key as keyof FilterValues] !== EMPTY_FILTERS[key as keyof FilterValues],
  );

  // Build the option list for one dropdown, emitting the unfiltered default
  // exactly once.
  //
  // Keep an active value selectable even when it is not part of the loaded
  // option list (for example a broad home-page category such as "Computing"
  // that the API returns department-level fields for). Without this the browser
  // would silently fall back to the first option ("Any field").
  //
  // The default must be filtered out of the supplied list and must not be
  // re-added as an "active" value: doing so rendered it twice in the unfiltered
  // state, because the current value *is* the default before any filter is
  // touched. Duplicates coming from the supplied list are removed too.
  const optionsWithDefault = (list: string[], current: string, placeholder: string) => {
    const deduped = Array.from(
      new Set(list.filter((value) => value && value !== placeholder)),
    );
    if (current && current !== placeholder && !deduped.includes(current)) {
      deduped.unshift(current);
    }
    return [placeholder, ...deduped];
  };

  const universityOptions = optionsWithDefault(
    merged.universities,
    values.university,
    EMPTY_FILTERS.university,
  );
  const fieldOptions = optionsWithDefault(merged.fields, values.field, EMPTY_FILTERS.field);
  const stateOptions = optionsWithDefault(merged.states, values.state, EMPTY_FILTERS.state);
  const verificationOptions = optionsWithDefault(
    merged.verificationStatuses,
    values.verification,
    EMPTY_FILTERS.verification,
  );
  const opportunityOptions = optionsWithDefault(
    merged.opportunitySignals,
    values.opportunity,
    EMPTY_FILTERS.opportunity,
  );

  const set = (key: keyof FilterValues, value: string) => {
    onChange({ ...values, [key]: value });
  };

  const clear = () => {
    onChange({ ...EMPTY_FILTERS });
  };

  return (
    <div className="card p-4">
      {activeFilters.length ? (
        <div className="mb-4" aria-label="Active filters" role="region">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Active filters</p>
          <ul className="flex flex-wrap gap-2">
            {activeFilters.map(({ key, label }) => (
              <li key={key} className="max-w-full break-words rounded-control border border-brand-200 bg-brand-50 px-2.5 py-1 text-xs text-brand-700">
                <span className="font-semibold">{label}:</span> {values[key as keyof FilterValues]}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Select
          id="filter-university"
          label="University"
          options={universityOptions}
          value={values.university}
          onChange={(event) => set("university", event.target.value)}
        />
        <Select
          id="filter-field"
          label="Field"
          options={fieldOptions}
          value={values.field}
          onChange={(event) => set("field", event.target.value)}
        />
        <Select
          id="filter-state"
          label="State"
          options={stateOptions}
          value={values.state}
          onChange={(event) => set("state", event.target.value)}
        />
      </div>

      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        Coverage varies by university. This directory includes selected researchers, not every faculty member.
      </p>

      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="focus-ring inline-flex items-center gap-1.5 rounded-control px-2 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
          aria-expanded={expanded}
          aria-controls="more-filters"
        >
          <Filter className="h-4 w-4" aria-hidden="true" />
          More filters
          <ChevronDown
            className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
        {touched ? (
          <button
            type="button"
            onClick={clear}
            className="focus-ring inline-flex items-center gap-1.5 rounded-control px-2 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Reset filters
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div id="more-filters" className="mt-3 grid grid-cols-1 gap-3 border-t border-border pt-3 sm:grid-cols-2">
          <Select
            id="filter-verification"
            label="Verification"
            options={verificationOptions}
            value={values.verification}
            onChange={(event) => set("verification", event.target.value)}
          />
          <Select
            id="filter-opportunity"
            label="Opportunity signals"
            options={opportunityOptions}
            value={values.opportunity}
            onChange={(event) => set("opportunity", event.target.value)}
          />
        </div>
      ) : null}
    </div>
  );
}

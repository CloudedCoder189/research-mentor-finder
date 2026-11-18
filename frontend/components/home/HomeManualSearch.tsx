"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { EMPTY_FILTERS, FilterBar, type FilterValues } from "@/components/search/FilterBar";
import { Button } from "@/components/ui/Button";

/**
 * Astra-style manual search block for the homepage: one wide search field with a
 * blue Search button, and the shared filter bar (University / Field / State +
 * More filters) beneath it. Submitting hands the query and filters to Discover.
 */
export function HomeManualSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<FilterValues>({ ...EMPTY_FILTERS });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const params = new URLSearchParams();
    const trimmed = query.trim();
    if (trimmed) params.set("q", trimmed);
    for (const [key, value] of Object.entries(filters)) {
      if (value !== EMPTY_FILTERS[key as keyof FilterValues]) params.set(key, value);
    }
    const search = params.toString();
    void router.push(search ? `/discover?${search}` : "/discover");
  };

  return (
    <form onSubmit={submit} role="search" className="w-full">
      <label htmlFor="home-search-input" className="sr-only">
        Search researchers
      </label>
      <div className="flex w-full flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-brand-500"
            aria-hidden="true"
          />
          <input
            id="home-search-input"
            type="search"
            value={query}
            maxLength={300}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Describe the research you’re interested in…"
            className="focus-ring h-12 w-full rounded-xl border border-border bg-surface pl-12 pr-4 text-sm text-ink-900 shadow-card placeholder:text-slate-400"
          />
        </div>
        <Button type="submit" size="lg" className="h-12 rounded-xl px-8">
          Search
        </Button>
      </div>

      <div className="mt-4">
        <FilterBar values={filters} onChange={setFilters} />
      </div>
    </form>
  );
}

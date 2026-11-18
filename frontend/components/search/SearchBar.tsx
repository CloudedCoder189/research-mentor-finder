"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export function SearchBar({
  onSearch,
  value,
  onValueChange,
  initialValue = "",
  maxLength = 300,
  placeholder = "Describe the research you’re interested in…",
  align = "center",
  autoFocus = false,
  className,
}: {
  onSearch: (query: string) => void;
  value?: string;
  onValueChange?: (query: string) => void;
  initialValue?: string;
  maxLength?: number;
  placeholder?: string;
  align?: "center" | "start";
  autoFocus?: boolean;
  className?: string;
}) {
  const [internalQuery, setInternalQuery] = useState(initialValue);
  const controlled = value !== undefined;
  const query = controlled ? value : internalQuery;

  const submit = () => {
    onSearch(query.trim());
  };

  const aligned = align === "center" ? "mx-auto" : "";

  return (
    <form
      className={cn(aligned, "w-full", className)}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      role="search"
    >
      <label htmlFor="search-input" className="sr-only">
        Search researchers
      </label>
      <div className={cn("flex w-full max-w-2xl gap-2", aligned)}>
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-brand-500"
            aria-hidden="true"
          />
          <input
            id="search-input"
            type="search"
            value={query}
            autoFocus={autoFocus}
            maxLength={maxLength}
            placeholder={placeholder}
            onChange={(event) => {
              const next = event.target.value;
              if (controlled) {
                onValueChange?.(next);
              } else {
                setInternalQuery(next);
              }
            }}
            className="focus-ring h-12 w-full rounded-xl border border-border bg-surface pl-12 pr-4 text-sm text-ink-900 shadow-card placeholder:text-slate-400"
            aria-describedby="search-help"
          />
        </div>
        <Button type="submit" size="lg" className="h-12 shrink-0 rounded-xl px-6">
          Search
        </Button>
      </div>
      <p id="search-help" className={cn("mt-2 text-xs text-slate-500", aligned ? "text-center" : "")}>
        Try: <span className="font-medium text-ink-600">AI for climate change</span> ·{" "}
        <span className="font-medium text-ink-600">neuroscience and memory</span>
      </p>
    </form>
  );
}
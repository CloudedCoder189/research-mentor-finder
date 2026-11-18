import type { Metadata } from "next";
import { DiscoverClient } from "@/components/search/DiscoverClient";

export const metadata: Metadata = {
  title: "Discover researchers",
};

const asString = (value: string | string[] | undefined): string =>
  typeof value === "string" ? value : "";

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string | string[];
    university?: string | string[];
    field?: string | string[];
    state?: string | string[];
    verification?: string | string[];
    opportunity?: string | string[];
  }>;
}) {
  const values = await searchParams;
  const initialQuery = asString(values.q);
  const initialFilters = {
    university: asString(values.university),
    field: asString(values.field),
    state: asString(values.state),
    verification: asString(values.verification),
    opportunity: asString(values.opportunity),
  };

  return <DiscoverClient initialQuery={initialQuery} initialFilters={initialFilters} />;
}

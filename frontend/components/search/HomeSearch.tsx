"use client";

import { useRouter } from "next/navigation";
import { SearchBar } from "@/components/search/SearchBar";

export function HomeSearch() {
  const router = useRouter();
  return (
    <SearchBar
      onSearch={(query) => {
        void router.push(`/discover?q=${encodeURIComponent(query)}`);
      }}
    />
  );
}
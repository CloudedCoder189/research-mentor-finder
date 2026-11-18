import type { Metadata } from "next";
import { ProfilePageView } from "@/components/researcher/profile/ProfilePageView";
import { discoverReturn } from "@/lib/discoverReturn";

export const metadata: Metadata = {
  title: "Researcher profile",
};

export default async function ResearcherProfilePage({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const { id } = await params;
  const { returnTo } = await searchParams;
  return <ProfilePageView id={id} discoverHref={discoverReturn(returnTo)} />;
}

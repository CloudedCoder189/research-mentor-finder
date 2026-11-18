import type { Metadata } from "next";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import { LiveComposer } from "@/components/outreach/Composer";

export const metadata: Metadata = {
  title: "Compose outreach email",
};

export default async function ComposePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <RequireAuth>
      <LiveComposer researcherId={id} />
    </RequireAuth>
  );
}

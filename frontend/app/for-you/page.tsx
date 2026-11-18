import { Container } from "@/components/ui/Container";
import { ForYouView } from "@/components/recommendations/ForYouView";
import { RequireAuth } from "@/components/auth/SignInPrompt";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "For you",
};

export default function ForYouPage() {
  return (
    <RequireAuth>
      <Container className="py-10 sm:py-12">
        <ForYouView />
      </Container>
    </RequireAuth>
  );
}
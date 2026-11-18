import { FileQuestion } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { LinkButton } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";

export default function NotFound() {
  return (
    <Container className="py-16 sm:py-24">
      <EmptyState
        icon={<FileQuestion className="h-6 w-6" aria-hidden="true" />}
        title="Page not found"
        description="That page doesn’t exist or the researcher may no longer be listed."
        action={<LinkButton href="/discover">Browse researchers</LinkButton>}
      />
    </Container>
  );
}
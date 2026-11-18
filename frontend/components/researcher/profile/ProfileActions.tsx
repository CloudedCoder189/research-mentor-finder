"use client";

import { LogIn, Mail } from "lucide-react";
import { SaveButton } from "@/components/researcher/SaveButton";
import { Button, LinkButton } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";

export function ProfileActions({ researcherId }: { researcherId: string }) {
  const { user, status, signIn } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex flex-wrap items-center gap-2" aria-hidden="true">
        <span className="inline-flex h-10 w-28 animate-pulse rounded-control bg-slate-200" />
        <span className="inline-flex h-10 w-36 animate-pulse rounded-control bg-slate-200" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={signIn}>
          <LogIn className="h-4 w-4" aria-hidden="true" />
          Sign in to save &amp; draft
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <SaveButton researcherId={researcherId} />
      <LinkButton href={`/outreach/compose/${researcherId}`}>
        <Mail className="h-4 w-4" aria-hidden="true" />
        Draft outreach email
      </LinkButton>
    </div>
  );
}
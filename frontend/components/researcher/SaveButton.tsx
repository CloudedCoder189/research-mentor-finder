"use client";

import { Bookmark, BookmarkCheck, Loader2 } from "lucide-react";
import { useId, useState } from "react";
import { useSaved } from "@/components/saved/SavedProvider";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";

type SaveButtonProps = { researcherId: string; size?: "sm" | "md" };

export function SaveButton(props: SaveButtonProps) {
  const { user } = useAuth();
  return <AccountSaveButton key={`${user?.user_id ?? "anonymous"}:${props.researcherId}`} {...props} />;
}

function AccountSaveButton({
  researcherId,
  size = "md",
}: SaveButtonProps) {
  const { isSaved, toggleSaved, status } = useSaved();
  const { user, status: authStatus, signIn } = useAuth();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const errorId = useId();

  const saved = isSaved(researcherId);
  const busy = pending || status === "loading";

  const toggle = () => {
    if (authStatus !== "ready" || !user) {
      signIn();
      return;
    }
    setFailed(false);
    setPending(true);
    void toggleSaved(researcherId).then((next) => {
      setFailed(!next);
      setPending(false);
    });
  };

  return (
    <span className="inline-flex max-w-full flex-col items-start gap-1">
    <Button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={saved}
      aria-busy={busy}
      aria-label={saved ? "Remove from saved" : "Save researcher"}
      aria-describedby={failed ? errorId : undefined}
      variant={saved ? "secondary" : "ghost"}
      size={size}
    >
      {busy ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : saved ? (
        <BookmarkCheck className="h-4 w-4 text-accent-600" aria-hidden="true" />
      ) : (
        <Bookmark className="h-4 w-4" aria-hidden="true" />
      )}
      {saved ? "Saved" : "Save"}
    </Button>
    {failed ? <span id={errorId} role="alert" className="max-w-44 text-xs text-rose-700">Could not update Saved. Try again.</span> : null}
    </span>
  );
}
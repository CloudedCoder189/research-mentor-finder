import { AlertTriangle, BadgeCheck, Eye, Clock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { VERIFICATION_META } from "@/lib/meta";
import type { VerificationStatus } from "@/types";

const ICONS: Record<VerificationStatus, typeof BadgeCheck> = {
  Verified: BadgeCheck,
  Review: Eye,
  Failed: AlertTriangle,
  "Not checked": Clock,
};

export function VerifiedBadge({
  status,
  showNote = false,
}: {
  status: VerificationStatus;
  showNote?: boolean;
}) {
  const meta = VERIFICATION_META[status];
  const Icon = ICONS[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge className={meta.pill} tone="neutral">
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {meta.label}
      </Badge>
      {showNote ? <span className="sr-only">{meta.note}</span> : null}
    </span>
  );
}
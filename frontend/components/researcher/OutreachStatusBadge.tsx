import { Badge } from "@/components/ui/Badge";
import { OUTREACH_STATUS_META } from "@/lib/meta";
import type { OutreachStatus } from "@/types";

export function OutreachStatusBadge({ status }: { status: OutreachStatus }) {
  const meta = OUTREACH_STATUS_META[status];
  return (
    <Badge className={meta.pill} tone="neutral">
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}
import { Badge } from "@/components/ui/Badge";
import { MATCH_META } from "@/lib/meta";
import type { MatchLabel } from "@/types";

export function MatchBadge({ label }: { label: MatchLabel }) {
  const meta = MATCH_META[label];
  return (
    <Badge className={meta.pill} tone="neutral">
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden="true" />
      {label}
    </Badge>
  );
}
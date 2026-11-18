import { cn } from "@/lib/cn";

type PillTone =
  | "neutral"
  | "brand"
  | "accent"
  | "emerald"
  | "amber"
  | "rose"
  | "violet"
  | "teal";

const TONES: Record<PillTone, string> = {
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
  brand: "border-brand-100 bg-brand-50 text-brand-700",
  accent: "border-accent-200 bg-accent-50 text-accent-700",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  rose: "border-rose-200 bg-rose-50 text-rose-700",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
  teal: "border-teal-200 bg-teal-50 text-teal-700",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: PillTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export { TONES as BADGE_TONES };
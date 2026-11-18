import Link from "next/link";
import { cn } from "@/lib/cn";

/** Thin outlined open-book mark (Astra brand style). Stroke-only, no fill. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("h-6 w-6 shrink-0", className)}
    >
      <path d="M12 6.6C10.7 5.2 8.7 4.5 6.2 4.5c-.8 0-1.5.06-2.2.18v13.1c.7-.12 1.4-.18 2.2-.18 2.5 0 4.5.7 5.8 1.9 1.3-1.2 3.3-1.9 5.8-1.9.8 0 1.5.06 2.2.18V4.68c-.7-.12-1.4-.18-2.2-.18-2.5 0-4.5.7-5.8 1.92Z" />
      <path d="M12 6.6v12.9" />
    </svg>
  );
}

export function BrandWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("min-w-0 [overflow-wrap:anywhere] text-base font-semibold tracking-tight text-ink-950", className)}>
      Research Mentor <span className="text-brand-600">Finder</span>
    </span>
  );
}

/**
 * Brand lockup: outlined open-book mark + wordmark.
 * Renders as a link to the homepage unless `href` is explicitly set to null.
 */
export function Brand({
  href = "/",
  markClassName,
  className,
  markTone = "text-brand-600",
}: {
  href?: string | null;
  markClassName?: string;
  className?: string;
  markTone?: string;
}) {
  const inner = (
    <span className={cn("flex min-w-0 items-center gap-2", className)}>
      <BrandMark className={cn(markTone, markClassName)} />
      <BrandWordmark />
    </span>
  );

  if (href === null) return inner;

  return (
    <Link
      href={href}
      className="focus-ring rounded-control"
      aria-label="Research Mentor Finder home"
    >
      {inner}
    </Link>
  );
}

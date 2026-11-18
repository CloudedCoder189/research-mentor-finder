import { Bookmark, Link2 } from "lucide-react";
import Link from "next/link";
import { MatchBadge } from "@/components/researcher/MatchBadge";
import type { HomePreviewResearcher } from "@/data/homePreview";

/**
 * Astra-style homepage preview row: identity (left) · why you match (center) ·
 * match label + actions (right). No avatar/photo. Preview rows are illustrative,
 * so Save is inert and "View profile" routes to a real Discover search.
 */
export function PreviewResearcherRow({ preview }: { preview: HomePreviewResearcher }) {
  const profileHref = `/discover?q=${encodeURIComponent(preview.searchQuery)}`;

  return (
    <article className="card p-4 sm:p-5" aria-label={`${preview.name} (illustrative preview)`}>
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-stretch lg:gap-5">
        <div className="lg:col-span-5">
          <div className="flex h-full flex-col gap-3">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-ink-900">{preview.name}</h3>
              <p className="mt-1 text-sm text-slate-600">{preview.university}</p>
              <p className="mt-0.5 text-sm text-slate-500">{preview.department}</p>
            </div>
            <ul className="flex flex-wrap gap-1.5">
              {preview.topics.map((topic) => (
                <li key={topic} className="chip-light">
                  {topic}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="lg:col-span-4">
          <div className="panel-aqua flex h-full flex-col gap-2 p-5">
            <p className="inline-flex items-center gap-2 text-sm font-semibold text-accent-700">
              <Link2 className="h-4 w-4" aria-hidden="true" />
              Why you match
            </p>
            <p className="text-sm leading-relaxed text-ink-700">{preview.whyMatch}</p>
          </div>
        </div>

        <div className="lg:col-span-3">
          <div className="flex h-full flex-col items-start gap-3">
            <MatchBadge label={preview.matchLabel} />
            <Link
              href={profileHref}
              className="focus-ring inline-flex h-11 w-full items-center justify-center rounded-control bg-brand-600 px-5 text-sm font-medium text-white shadow-card transition-colors hover:bg-brand-700"
            >
              View profile
            </Link>
            <button
              type="button"
              disabled
              title="Saving becomes available on Discover and For You once you sign in."
              className="focus-ring inline-flex h-10 w-full cursor-not-allowed items-center justify-center gap-2 rounded-control border border-border bg-surface px-4 text-sm font-medium text-slate-400"
            >
              <Bookmark className="h-4 w-4" aria-hidden="true" />
              Save
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

export function ResearchTopicTags({ topics, max }: { topics: string[]; max?: number }) {
  const shown = max ? topics.slice(0, max) : topics;
  const remaining = max ? Math.max(0, topics.length - max) : 0;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Research topics">
      {shown.map((topic) => (
        <li key={topic} className="chip-light">
          {topic}
        </li>
      ))}
      {remaining > 0 ? (
        <li className="rounded-pill border border-slate-200 bg-surface px-2.5 py-0.5 text-xs font-medium text-slate-500">
          +{remaining} more
        </li>
      ) : null}
    </ul>
  );
}
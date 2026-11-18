import { Compass, Library } from "lucide-react";

export function LearningIntro({ title, eyebrow, children, kind }: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
  kind: "starter" | "opportunities";
}) {
  const Icon = kind === "starter" ? Compass : Library;
  return <div className="learning-intro">
    <div className="learning-intro-icon" aria-hidden="true"><Icon className="h-6 w-6" /></div>
    <div className="min-w-0 max-w-3xl">
      <p className="learning-eyebrow">{eyebrow}</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-950 sm:text-4xl">{title}</h1>
      <p className="mt-4 max-w-2xl leading-relaxed text-ink-600">{children}</p>
    </div>
  </div>;
}

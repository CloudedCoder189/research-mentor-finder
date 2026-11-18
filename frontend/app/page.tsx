import { Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { Container } from "@/components/ui/Container";

export default function HomePage() {
  return (
    <div>
      <section className="border-b border-border bg-surface">
        <Container className="py-10 sm:py-14">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
              Your next research chapter starts here
            </p>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-ink-950 sm:text-5xl">
              Find research mentors
              <span className="block text-brand-600">who match you</span>
            </h1>
            <p className="mx-auto mt-3 max-w-2xl text-base text-slate-500">
              Tell us what you care about, and we’ll surface faculty who publish in that space —
              drawn only from official university sources.
            </p>

            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <LinkButtonPrimary href="/discover">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                Explore researchers
              </LinkButtonPrimary>
              <LinkButtonSecondary href="/for-you">
                <Search className="h-4 w-4" aria-hidden="true" />
                Get personalized matches
              </LinkButtonSecondary>
            </div>

            <div className="mt-5 space-y-1">
              <p className="mb-4 text-sm"><Link href="/start-research" className="focus-ring rounded-control font-semibold text-brand-700 underline">New to research? Find your first step</Link></p>
              <p className="text-sm font-medium text-slate-500">
                Free for high-school and college students · Start with your interests, build your profile as
                you go.
              </p>
              <p className="text-sm text-slate-400">
                Research discovery · Personalized matching · Search by research interests
              </p>
            </div>
          </div>
        </Container>
      </section>

      <section className="py-10 sm:py-12">
        <Container>
          <div className="mx-auto grid max-w-4xl gap-6 sm:grid-cols-3">
            {[
              ["1. Explore", "Search real university profiles by topic and location. A research match does not mean a mentoring opening."],
              ["2. Choose", "Read the source evidence, save a shortlist, and compare researchers before deciding whom to contact."],
              ["3. Reach out", "Create a draft from your own background, add a specific question, and send it yourself when ready."],
            ].map(([title, description]) => <div key={title}><h2 className="text-lg font-semibold text-ink">{title}</h2><p className="mt-2 text-sm text-slate-500">{description}</p></div>)}
          </div>
        </Container>
      </section>
    </div>
  );
}

function LinkButtonPrimary({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex h-12 items-center justify-center gap-2 rounded-control bg-brand-600 px-5 text-base font-medium text-white shadow-card transition-colors hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2"
    >
      {children}
    </Link>
  );
}

function LinkButtonSecondary({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex h-12 items-center justify-center gap-2 rounded-control border border-border bg-surface px-5 text-base font-medium text-ink shadow-card transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2"
    >
      {children}
    </Link>
  );
}

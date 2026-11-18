import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "About",
};

export default function AboutPage() {
  return (
    <Container className="py-10 sm:py-12">
      <PageHeader
        title="About Research Mentor Finder"
        description="A research directory for high-school and undergraduate students who want to find faculty whose published work matches their interests."
      />

      <div className="prose-slate mt-8 max-w-3xl space-y-6 text-sm leading-relaxed text-ink-600">
        <section>
          <h2 className="text-base font-semibold text-ink">What this is</h2>
          <p className="mt-2">
            Research Mentor Finder helps you search a directory of faculty and researchers by
            describing a research area in your own words. It can also rank that directory against a
            short profile you build about your own interests, and help you draft an outreach email
            to a researcher.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Where the records come from</h2>
          <p className="mt-2">
            Every researcher record is collected from official university sources such as faculty
            directories and department pages. Each record keeps the source it came from, when it was
            last checked, and a verification status, so you can see how current the information is.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">What it does not do</h2>
          <p className="mt-2">
            Nothing is ever sent on your behalf. Outreach emails are drafts that you review and send
            yourself, and we never read the body of your messages. Titles, affiliations, and research
            areas occasionally need manual correction; if you spot something that looks wrong, use
            the Contact page to report it.
          </p>
        </section>
      </div>
    </Container>
  );
}
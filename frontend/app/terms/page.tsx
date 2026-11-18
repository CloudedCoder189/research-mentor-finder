import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Terms",
};

export default function TermsPage() {
  return (
    <Container className="py-10 sm:py-12">
      <PageHeader
        title="Terms of use"
        description="The ground rules for using the directory and the tools built on top of it."
      />

      <div className="mt-8 max-w-3xl space-y-6 text-sm leading-relaxed text-ink-600">
        <section>
          <h2 className="text-base font-semibold text-ink">How to use this site</h2>
          <p className="mt-2">
            Use the directory to find researchers whose work you are genuinely interested in. When you
            reach out, be specific about what drew you to their work, keep it brief, and be easy to
            say no to. Treat people as colleagues, not as a list of names.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Drafts, not sending</h2>
          <p className="mt-2">
            Outreach tools produce drafts for you to review and send yourself. You are responsible for
            what you send. Do not use the site to send bulk or repeated unsolicited messages.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Accuracy of records</h2>
          <p className="mt-2">
            Records are collected from official sources but cannot be guaranteed complete or current.
            Verify details on a researcher&apos;s official page before you rely on them, and treat
            verification badges as a signal rather than a guarantee.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">No guarantee</h2>
          <p className="mt-2">
            Matches, explanations, and scores are suggestions produced from published text. They are
            not admissions advice, and no relationship with any researcher is implied.
          </p>
        </section>
      </div>
    </Container>
  );
}
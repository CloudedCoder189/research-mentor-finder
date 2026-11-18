import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Contact",
};

export default function ContactPage() {
  return (
    <Container className="py-10 sm:py-12">
      <PageHeader
        title="Contact"
        description="How to report a bad record, ask a question, or get in touch."
      />

      <div className="mt-8 max-w-3xl space-y-6 text-sm leading-relaxed text-ink-600">
        <section>
          <h2 className="text-base font-semibold text-ink">Reaching a researcher</h2>
          <p className="mt-2">
            The fastest route to a researcher is the official faculty page linked from their profile
            on this site. Those links go straight to the university&apos;s own site, which is the
            authoritative place for contact details and availability.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Reporting a data problem</h2>
          <p className="mt-2">
            If a record shows a title, department, or affiliation that looks wrong, note the
            researcher and what the official page says instead, and include the university. Records
            are corrected through the source, so specific corrections are the ones that stick.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Contact address</h2>
          <p className="mt-2">
            For help, privacy requests, or corrections to a researcher record, email{" "}
            <a
              href="mailto:researchmentorfinder@gmail.com"
              className="focus-ring rounded-control break-all font-medium text-brand-700 hover:underline"
            >
              researchmentorfinder@gmail.com
            </a>
            . Include the researcher&apos;s name and official source link when reporting a correction.
            Please do not send passwords, access tokens, or sensitive personal documents.
          </p>
          <p className="mt-2">
            You can also read how the directory is put together on the{" "}
            <Link href="/about" className="focus-ring rounded-control font-medium text-brand-700 hover:underline">
              About
            </Link>{" "}
            and{" "}
            <Link href="/privacy" className="focus-ring rounded-control font-medium text-brand-700 hover:underline">
              Privacy
            </Link>{" "}
            pages.
          </p>
        </section>
      </div>
    </Container>
  );
}

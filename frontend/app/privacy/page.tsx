import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Privacy",
};

export default function PrivacyPage() {
  return (
    <Container className="py-10 sm:py-12">
      <PageHeader
        title="Privacy"
        description="What this site stores, why, and what it deliberately does not collect."
      />

      <div className="mt-8 max-w-3xl space-y-6 text-sm leading-relaxed text-ink-600">
        <section>
          <h2 className="text-base font-semibold text-ink">Public browsing</h2>
          <p className="mt-2">
            Searching the directory needs no account. Searches and the filters you choose are sent to
            the server to run the search. The app does not keep an account-linked search history.
            Server logs and any existing search caches may still contain request information.
          </p>
          <p className="mt-2">
            To limit excessive requests, the app temporarily counts requests using a protected
            identifier derived from your network address. These counters stay in server memory,
            expire after their short limit window, and are not saved as account history.
            People using the same network may share a limit.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Aggregate usage measurement</h2>
          <p className="mt-2">We count page categories and successful feature requests in daily totals to understand whether the site is useful. These counters store no names, emails, account or visitor identifiers, network addresses, search text, résumé content, or researcher IDs. They use no analytics cookies or third-party analytics service. Repeated actions count again; this does not measure unique visitors. Daily totals are kept for 90 days. Collection respects Do Not Track and Global Privacy Control signals where available. A private owner dashboard also shows the total number of Google accounts still stored. Hosting providers may maintain separate request logs.</p>
          <p className="mt-2">A profile’s report-issue link opens an email draft with the public researcher’s name and profile link. Nothing is sent until you choose to send it. Your email provider handles that message under its own policies.</p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Research starting notes and pathway filters</h2>
          <p className="mt-2">Interests and starting notes entered in Research Starter, and school-level filters in the opportunity collection, stay in the current page. They are not saved to your account or sent to AI. Refreshing or leaving the page discards them. Copying notes puts them on your device clipboard. Opening a provider link takes you to a separate website governed by its own policies.</p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Optional AI explanations</h2>
          <p className="mt-2">
            Paid AI explanations are disabled in this release. If enabled in a future
            release, requesting one sends selected interests, skills, coursework, and preferences
            with public researcher information to the AI provider. Account addresses, private
            outreach notes, and Gmail contents are excluded from that explanation context.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Hosting and service providers</h2>
          <p className="mt-2">Unsaved outreach edits may be kept temporarily in this browser tab for recovery. They are separate for each account and cleared after a successful save, sign-out, or account deletion in this tab. Closing the tab clears its temporary draft recovery; use Save draft to keep edits in your account.</p>
            <p className="mt-2">Shortlist comparison selections are also stored separately for each account in this browser tab. They clear when you sign out, delete your account in this tab, or close the tab; selections do not synchronize across devices.</p>
          <p className="mt-2">
            The hosted app runs on Railway. Account profiles, saved researchers, and outreach
            records are stored on the server. Encrypted managed backups and deletion receipts are
            stored separately in private Railway storage; the backup decryption key is kept outside
            that storage. Railway provides both the app hosting and backup storage.
          </p>
          <p className="mt-2">
            Google handles sign-in and supplies your account identifier, email address, name, and
            profile image. Connecting Gmail is a separate optional permission; it is currently
            unavailable in the hosted release. Your sign-in does not by itself grant Gmail access.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Keeping and removing your data</h2>
          <p className="mt-2">
            Signing out ends your session; it does not delete your profile, saved researchers, or
            outreach records. We keep live account data until you choose Delete my account on the
            account page. Deletion removes your live profile, saved researchers, outreach records,
            sessions, stored Gmail credentials and account-linked pending connections. Signing in
            again creates an empty account. Your messages and drafts already in Gmail are unaffected.
          </p>
          <p className="mt-2">
            We attempt to revoke Gmail access with Google. If Google cannot confirm revocation,
            local credentials are still removed and the deletion result directs you to your Google
            Account connections. A minimal receipt containing a hash of the account identifier and
            deletion time is retained to prevent accidentally restoring deleted account data.
          </p>
          <p className="mt-2">
            New managed backups are encrypted and made daily. Managed backups and operational logs
            expire after 30 days, checked at server startup and hourly while the server is running.
            Expiry catches up after downtime. Managed logs contain event categories rather than
            request contents. An independent deletion ledger is kept without automatic expiry;
            operators must apply it before restoring a backup.
          </p>
          <p className="mt-2">
            Historical manual backups, logs and review evidence remain outside this managed policy.
            Deletion does not erase those older copies, browser data on other devices, or data held
            by Google or an AI provider. Historical copies need an explicit retention decision
            before public launch. Public researcher records are retained separately from account data.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">When you sign in</h2>
          <p className="mt-2">
            Signing in stores your saved researchers, outreach records, profile, and any Gmail
            connection against your account. Your session is held in an HttpOnly cookie and expires
            after a fixed number of days. A non-identifying change signal is stored in browser storage so open tabs can recheck sign-in. It contains no account identifier or session token.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Email handling</h2>
          <p className="mt-2">
            If you connect Gmail, the app requests permission to create drafts and to read message
            metadata so it can check whether your draft was sent or a reply arrived. Message bodies
            are never read, and no email
            is ever sent automatically.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Résumé import</h2>
          <p className="mt-2">
            Choosing a résumé sends its contents to our server for text extraction. The original
            file and extracted preview are not saved by the app or sent to an AI provider.
            Review and edit the suggestions before applying them. Only the skills, coursework,
            and experience you apply become part of your stored profile and its managed backups.
            The selected filename stays in this browser. Do not import details you want to keep private.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Public researcher data</h2>
          <p className="mt-2">
            Researcher names, titles, departments, and published contact details come from official
            university sources and are public information. We collect them to help you find a
            mentor, not to build a profile about you.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-ink">Questions and privacy requests</h2>
          <p className="mt-2">
            For questions about your data or help with a privacy request, email{" "}
            <a
              href="mailto:researchmentorfinder@gmail.com"
              className="focus-ring rounded-control break-all font-medium text-brand-700 hover:underline"
            >
              researchmentorfinder@gmail.com
            </a>
            . Please do not include passwords, access tokens, or sensitive personal documents.
          </p>
        </section>
      </div>
    </Container>
  );
}

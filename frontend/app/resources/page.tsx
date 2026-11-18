import Link from "next/link";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";

export default function ResourcesPage() {
  return <Container className="py-10 sm:py-12">
    <PageHeader title="Research resources" description="Optional guidance for your first research experience. You can explore researchers without completing these activities." />
    <div className="mt-8 grid gap-6 md:grid-cols-2">
      <section className="card p-6"><h2 className="text-xl font-semibold">New to research?</h2><p className="mt-3 text-slate-500">Explore a research direction, learn common terms, and try a small introductory activity.</p><Link className="focus-ring mt-5 inline-block rounded-control font-semibold text-brand-700 underline" href="/start-research">Explore learning guides</Link></section>
      <section className="card p-6"><h2 className="text-xl font-semibold">Looking for a structured pathway?</h2><p className="mt-3 text-slate-500">Review source-confirmed program pathways and check their eligibility and current dates on the official site. A listing does not guarantee admission or an open place.</p><Link className="focus-ring mt-5 inline-block rounded-control font-semibold text-brand-700 underline" href="/opportunities">Explore program pathways</Link></section>
    </div>
  </Container>;
}

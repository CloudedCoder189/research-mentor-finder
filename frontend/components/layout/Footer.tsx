import Link from "next/link";
import { Brand } from "@/components/layout/Brand";
import { Container } from "@/components/ui/Container";

const FOOTER_LINKS = [
  { label: "About", href: "/about" },
  { label: "Privacy", href: "/privacy" },
  { label: "Terms", href: "/terms" },
  { label: "Contact", href: "/contact" },
];

export function Footer() {
  return (
    <footer className="border-t border-border bg-surface">
      <Container className="flex flex-col gap-6 py-8 sm:flex-row sm:items-center sm:justify-between">
        <Brand href="/" markTone="text-brand-600" />
        <nav aria-label="Footer">
          <ul className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {FOOTER_LINKS.map((link) => (
              <li key={link.label}>
                <Link
                  href={link.href}
                  className="focus-ring rounded-control text-sm text-slate-500 transition-colors hover:text-brand-700"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </Container>
    </footer>
  );
}

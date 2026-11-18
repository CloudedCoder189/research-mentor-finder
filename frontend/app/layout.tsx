import type { Metadata } from "next";
import { Footer } from "@/components/layout/Footer";
import { Nav } from "@/components/layout/Nav";
import { SavedProvider } from "@/components/saved/SavedProvider";
import { AuthProvider } from "@/lib/auth-context";
import "@/styles/globals.css";
import "@/styles/theme-toggle.css";
import { THEME_SCRIPT } from "@/lib/theme-script";
import { PageViews } from "@/components/usage/PageViews";

export const metadata: Metadata = {
  title: {
    default: "Research Mentor Finder",
    template: "%s · Research Mentor Finder",
  },
  description:
    "Find research mentors who match your interests. Explore researcher profiles, search by research topic, and discover potential mentors.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head>
      <body className="flex min-h-screen flex-col bg-paper text-ink">
        <AuthProvider>
          <PageViews />
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:shadow-card"
          >
            Skip to content
          </a>
          <Nav />
          <main id="main" tabIndex={-1} className="flex-1">
            <SavedProvider>{children}</SavedProvider>
          </main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}

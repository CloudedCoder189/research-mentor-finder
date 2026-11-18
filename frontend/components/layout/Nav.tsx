"use client";

import { LogIn, LogOut, Menu, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { Brand } from "@/components/layout/Brand";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/cn";
import { useDevToolsVisible } from "@/lib/use-dev-tools";

const NAV_ITEMS = [
  { href: "/discover", label: "Discover", key: "discover" },
  { href: "/for-you", label: "For You", key: "for-you" },
  { href: "/saved", label: "Saved", key: "saved" },
  { href: "/outreach", label: "Drafts", key: "outreach" },
  { href: "/resources", label: "Resources", key: "resources" },
];

const ACCOUNT_ITEM = { href: "/account", label: "Account", key: "account" };

function activeKey(pathname: string): string {
  if (pathname.startsWith("/researchers")) return "discover";
  if (pathname.startsWith("/start-research") || pathname.startsWith("/opportunities")) return "resources";
  if (pathname === "/") return "home";
  for (const item of [...NAV_ITEMS, ACCOUNT_ITEM]) {
    if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return item.key;
  }
  return "";
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const active = activeKey(pathname);
  const { user, status, signIn, signOut, devSignIn, devLoginAvailable, signOutError, signingOut } = useAuth();
  const showDevTools = useDevToolsVisible() && devLoginAvailable;

  return (
    <header className="app-navigation sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur-sm"
      onKeyDown={(event) => {
        if (open && event.key === "Escape") {
          event.preventDefault();
          setOpen(false);
          menuButton.current?.focus();
        }
      }}>
      <Container className="relative flex flex-wrap min-h-16 items-center justify-between gap-2 py-2 [&>a:first-child]:min-w-[min(100%,10rem)]">
        <Brand className="min-w-0 max-w-36 sm:max-w-none" markClassName="h-[24px] w-[24px]" />

        <nav aria-label="Primary" className="hidden 2xl:block">
          <ul className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.key}>
                <Link
                  href={item.href}
                  aria-current={active === item.key ? "page" : undefined}
                  className={cn(
                    "focus-ring inline-flex h-9 items-center rounded-pill px-3.5 text-sm font-medium transition-colors",
                    active === item.key
                      ? "bg-brand-50 text-brand-700"
                      : "text-ink-600 hover:bg-slate-100 hover:text-ink-950",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <ThemeToggle />
          <div className="hidden items-center gap-2 2xl:flex">
            <Link
              href={ACCOUNT_ITEM.href}
              aria-current={active === ACCOUNT_ITEM.key ? "page" : undefined}
              className={cn(
                "focus-ring inline-flex h-9 items-center rounded-pill px-3.5 text-sm font-medium transition-colors",
                active === ACCOUNT_ITEM.key
                  ? "bg-brand-50 text-brand-700"
                  : "text-ink-600 hover:bg-slate-100 hover:text-ink-950",
              )}
            >
              {ACCOUNT_ITEM.label}
            </Link>
            {status === "ready" ? (
              user ? (
                <>
                  <span
                    className="inline-flex max-w-40 items-center gap-1.5 truncate text-sm font-medium text-ink-600"
                    title={user.email}
                  >
                    <UserRound className="h-4 w-4 text-brand-600" aria-hidden="true" />
                    <span className="truncate">{user.display_name || user.email}</span>
                  </span>
                  <Button variant="ghost" size="sm" disabled={signingOut} onClick={() => void signOut()}>
                    <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                    Sign out
                  </Button>
                </>
              ) : (
                <>
                  <Button size="sm" onClick={signIn}>
                    <LogIn className="h-3.5 w-3.5" aria-hidden="true" />
                    Sign in
                  </Button>
                  {showDevTools ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void devSignIn()}
                      aria-label="Sign in with the local developer account"
                    >
                      Dev
                    </Button>
                  ) : null}
                </>
              )
            ) : null}
          </div>

          <button
            ref={menuButton}
            type="button"
            className="focus-ring inline-flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-control text-ink-600 hover:bg-slate-100 2xl:hidden"
            aria-expanded={open}
            aria-controls="mobile-navigation"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X className="h-[20px] w-[20px]" aria-hidden="true" /> : <Menu className="h-[20px] w-[20px]" aria-hidden="true" />}
          </button>
        </div>
      </Container>

      {signOutError ? <Container><p className="py-2 text-sm text-rose-700" role="alert">{signOutError}</p></Container> : null}
      {open ? (
        <nav id="mobile-navigation" aria-label="Mobile" className="border-t border-border bg-surface 2xl:hidden">
          <Container className="flex flex-col gap-1 py-3">
            {[...NAV_ITEMS, ACCOUNT_ITEM].map((item) => (
              <Link
                key={item.key}
                href={item.href}
                onClick={() => setOpen(false)}
                aria-current={active === item.key ? "page" : undefined}
                className={cn(
                  "focus-ring rounded-control px-3 py-2.5 text-sm font-medium",
                  active === item.key
                    ? "bg-brand-50 text-brand-700"
                    : "text-ink-600 hover:bg-slate-100",
                )}
              >
                {item.label}
              </Link>
            ))}
            <div className="mt-2 flex flex-wrap gap-2 border-t border-border pt-3">
              {status === "ready" ? (
                user ? (
                  <Button variant="ghost" className="w-full justify-center" disabled={signingOut} onClick={() => void signOut()}>
                    <LogOut className="h-4 w-4" aria-hidden="true" />
                    <span className="min-w-0 truncate">Sign out ({user.display_name || user.email})</span>
                  </Button>
                ) : (
                  <>
                    <Button className="flex-1 justify-center" onClick={signIn}>
                      <LogIn className="h-4 w-4" aria-hidden="true" />
                      Sign in
                    </Button>
                    {showDevTools ? (
                      <Button
                        variant="secondary"
                        className="flex-1 justify-center"
                        onClick={() => void devSignIn()}
                      >
                        Dev account
                      </Button>
                    ) : null}
                  </>
                )
              ) : null}
            </div>
          </Container>
        </nav>
      ) : null}
    </header>
  );
}

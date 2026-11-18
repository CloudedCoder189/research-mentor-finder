import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "outline" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "border border-transparent bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800",
  secondary:
    "border border-border bg-surface text-ink hover:border-brand-200 hover:bg-brand-50/60",
  ghost: "border border-transparent bg-transparent text-brand-700 hover:bg-brand-50",
  outline: "border border-brand-200 bg-surface text-brand-700 hover:bg-brand-50",
  danger:
    "border border-rose-200 bg-surface text-rose-700 hover:bg-rose-50 shadow-card",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-9 gap-1.5 px-3 py-1.5 text-sm",
  md: "min-h-11 gap-2 px-4 py-2 text-sm",
  lg: "min-h-12 gap-2 px-5 py-2.5 text-base",
};

const BASE =
  "app-button focus-ring inline-flex items-center justify-center rounded-control font-medium " +
  "transition-[background-color,border-color,box-shadow] duration-200 disabled:cursor-not-allowed disabled:opacity-60";

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: CommonProps &
  ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "primary",
  size = "md",
  className,
  children,
  href,
  ...rest
}: CommonProps & AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  return (
    <Link
      href={href}
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    >
      {children}
    </Link>
  );
}
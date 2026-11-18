import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./styles/**/*.css",
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          50: "rgb(var(--color-slate-50) / <alpha-value>)",
          100: "rgb(var(--color-slate-100) / <alpha-value>)",
          200: "rgb(var(--color-slate-200) / <alpha-value>)",
          300: "rgb(var(--color-slate-300) / <alpha-value>)",
          400: "rgb(var(--color-slate-400) / <alpha-value>)",
          500: "rgb(var(--color-slate-500) / <alpha-value>)",
          600: "rgb(var(--color-slate-600) / <alpha-value>)",
          700: "rgb(var(--color-slate-700) / <alpha-value>)",
          800: "rgb(var(--color-slate-800) / <alpha-value>)",
          900: "rgb(var(--color-slate-900) / <alpha-value>)",
        },
        amber: {
          50: "rgb(var(--color-amber-50) / <alpha-value>)",
          200: "rgb(var(--color-amber-200) / <alpha-value>)",
          500: "rgb(var(--color-amber-500) / <alpha-value>)",
          600: "rgb(var(--color-amber-600) / <alpha-value>)",
          700: "rgb(var(--color-amber-700) / <alpha-value>)",
          800: "rgb(var(--color-amber-800) / <alpha-value>)",
          900: "rgb(var(--color-amber-900) / <alpha-value>)",
        },
        blue: {
          50: "rgb(var(--color-blue-50) / <alpha-value>)",
          200: "rgb(var(--color-blue-200) / <alpha-value>)",
          500: "rgb(var(--color-blue-500) / <alpha-value>)",
          700: "rgb(var(--color-blue-700) / <alpha-value>)",
        },
        emerald: {
          50: "rgb(var(--color-emerald-50) / <alpha-value>)",
          200: "rgb(var(--color-emerald-200) / <alpha-value>)",
          500: "rgb(var(--color-emerald-500) / <alpha-value>)",
          700: "rgb(var(--color-emerald-700) / <alpha-value>)",
        },
        rose: {
          50: "rgb(var(--color-rose-50) / <alpha-value>)",
          200: "rgb(var(--color-rose-200) / <alpha-value>)",
          600: "rgb(var(--color-rose-600) / <alpha-value>)",
          700: "rgb(var(--color-rose-700) / <alpha-value>)",
        },
        red: {
          700: "rgb(var(--color-red-700) / <alpha-value>)",
        },

        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          50: "rgb(var(--color-ink-50) / <alpha-value>)",
          100: "rgb(var(--color-ink-100) / <alpha-value>)",
          200: "rgb(var(--color-ink-200) / <alpha-value>)",
          500: "rgb(var(--color-ink-500) / <alpha-value>)",
          600: "rgb(var(--color-ink-600) / <alpha-value>)",
          700: "rgb(var(--color-ink-700) / <alpha-value>)",
          800: "rgb(var(--color-ink-800) / <alpha-value>)",
          900: "rgb(var(--color-ink-900) / <alpha-value>)",
          950: "rgb(var(--color-ink-950) / <alpha-value>)",
        },
        brand: {
          50: "rgb(var(--color-brand-50) / <alpha-value>)",
          100: "rgb(var(--color-brand-100) / <alpha-value>)",
          200: "rgb(var(--color-brand-200) / <alpha-value>)",
          300: "rgb(var(--color-brand-300) / <alpha-value>)",
          400: "rgb(var(--color-brand-400) / <alpha-value>)",
          500: "rgb(var(--color-brand-500) / <alpha-value>)",
          600: "rgb(var(--color-brand-600) / <alpha-value>)",
          700: "rgb(var(--color-brand-700) / <alpha-value>)",
          800: "rgb(var(--color-brand-800) / <alpha-value>)",
          900: "rgb(var(--color-brand-900) / <alpha-value>)",
        },
        accent: {
          50: "rgb(var(--color-accent-50) / <alpha-value>)",
          100: "rgb(var(--color-accent-100) / <alpha-value>)",
          200: "rgb(var(--color-accent-200) / <alpha-value>)",
          300: "rgb(var(--color-accent-300) / <alpha-value>)",
          500: "rgb(var(--color-accent-500) / <alpha-value>)",
          600: "rgb(var(--color-accent-600) / <alpha-value>)",
          700: "rgb(var(--color-accent-700) / <alpha-value>)",
        },
        paper: "rgb(var(--color-paper) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.08)",
        panel:
          "0 1px 2px 0 rgb(15 23 42 / 0.05), 0 2px 6px -1px rgb(15 23 42 / 0.08)",
        focus: "0 0 0 3px rgb(37 99 235 / 0.25)",
      },
      borderRadius: {
        control: "0.5rem",
        card: "0.75rem",
        pill: "9999px",
      },
    },
  },
  plugins: [],
};

export default config;

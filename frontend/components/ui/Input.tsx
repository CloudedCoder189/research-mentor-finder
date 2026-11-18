import { AlertCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const SIZES: Record<"sm" | "md", string> = {
  sm: "px-3 py-2 text-sm h-9",
  md: "px-3.5 py-2.5 text-sm h-10",
};

export function Input({
  id,
  label,
  hint,
  fieldSize = "md",
  className,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label?: string;
  hint?: string;
  fieldSize?: "sm" | "md";
}) {
  return (
    <div className="w-full">
      {label ? (
        <label htmlFor={id} className="field-label">
          {label}
        </label>
      ) : null}
      <input
        id={id}
        className={cn(
          "focus-ring w-full rounded-control border border-border bg-surface px-3 text-ink shadow-card placeholder:text-slate-400",
          SIZES[fieldSize],
          className,
        )}
        {...rest}
      />
      {hint ? <p className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Textarea({
  id,
  label,
  hint,
  className,
  ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  id: string;
  label?: string;
  hint?: string;
}) {
  return (
    <div className="w-full">
      {label ? (
        <label htmlFor={id} className="field-label">
          {label}
        </label>
      ) : null}
      <textarea
        id={id}
        className={cn(
          "focus-ring w-full rounded-control border border-border bg-surface px-3 py-2.5 text-sm text-ink shadow-card placeholder:text-slate-400",
          className,
        )}
        {...rest}
      />
      {hint ? <p className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Select({
  id,
  label,
  hint,
  options,
  className,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  id: string;
  label?: string;
  hint?: string;
  options: ReadonlyArray<string>;
}) {
  return (
    <div className="w-full">
      {label ? (
        <label htmlFor={id} className="field-label">
          {label}
        </label>
      ) : null}
      <select
        id={id}
        className={cn(
          "focus-ring h-10 w-full rounded-control border border-border bg-surface px-3 text-sm text-ink shadow-card",
          className,
        )}
        {...rest}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {hint ? <p className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function InlineNotice({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "amber";
}) {
  const tones = {
    neutral: "border-slate-200 bg-slate-50 text-slate-600",
    brand: "border-brand-200 bg-brand-50 text-brand-700",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
  };
  return (
    <div className={cn("flex items-start gap-2 rounded-control border px-3 py-2.5 text-sm", tones[tone])}>
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
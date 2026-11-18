import type { MatchLabel, OutreachStatus, VerificationStatus, WebsiteStatus } from "@/types";

export const OUTREACH_STATUSES: OutreachStatus[] = [
  "Not contacted",
  "Drafted",
  "Sent",
  "Replied",
  "Meeting scheduled",
  "Follow-up due",
  "Closed",
];

export const OUTREACH_STATUS_META: Record<
  OutreachStatus,
  { label: string; dot: string; pill: string }
> = {
  "Not contacted": {
    label: "Not contacted",
    dot: "bg-slate-400",
    pill: "border-slate-200 bg-slate-50 text-slate-700",
  },
  Drafted: {
    label: "Drafted",
    dot: "bg-blue-500",
    pill: "border-blue-200 bg-blue-50 text-blue-700",
  },
  Sent: {
    label: "Sent",
    dot: "bg-violet-500",
    pill: "border-violet-200 bg-violet-50 text-violet-700",
  },
  Replied: {
    label: "Replied",
    dot: "bg-teal-600",
    pill: "border-teal-200 bg-teal-50 text-teal-700",
  },
  "Meeting scheduled": {
    label: "Meeting scheduled",
    dot: "bg-emerald-500",
    pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  "Follow-up due": {
    label: "Follow-up due",
    dot: "bg-amber-500",
    pill: "border-amber-200 bg-amber-50 text-amber-800",
  },
  Closed: {
    label: "Closed",
    dot: "bg-slate-500",
    pill: "border-slate-200 bg-slate-100 text-slate-600",
  },
};

export const VERIFICATION_META: Record<
  VerificationStatus,
  { label: string; pill: string; note: string }
> = {
  Verified: {
    label: "Verified academic profile",
    pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
    note: "Confirmed against the official faculty roster.",
  },
  Review: {
    label: "In review",
    pill: "border-amber-200 bg-amber-50 text-amber-800",
    note: "Record could not be fully confirmed; retained for review.",
  },
  Failed: {
    label: "Needs review",
    pill: "border-rose-200 bg-rose-50 text-rose-700",
    note: "Could not be web-confirmed; retained, not discarded.",
  },
  "Not checked": {
    label: "Pending review",
    pill: "border-slate-200 bg-slate-50 text-slate-600",
    note: "Awaiting a verification pass.",
  },
};

export const WEBSITE_META: Record<WebsiteStatus, { label: string; pill: string }> = {
  Verified: {
    label: "Site verified",
    pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  Review: {
    label: "Site in review",
    pill: "border-amber-200 bg-amber-50 text-amber-800",
  },
  Broken: {
    label: "Site broken",
    pill: "border-rose-200 bg-rose-50 text-rose-700",
  },
  "Not checked": {
    label: "Site not checked",
    pill: "border-slate-200 bg-slate-50 text-slate-600",
  },
};

export const MATCH_LABELS: MatchLabel[] = [
  "Strong match",
  "Good match",
  "Possible match",
  "Limited match",
  "Strong research match",
  "Good research match",
  "Potential match",
];

export const MATCH_META: Record<MatchLabel, { pill: string; dot: string }> = {
  "Strong match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-emerald-500",
  },
  "Good match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-brand-500",
  },
  "Possible match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-amber-500",
  },
  "Limited match": {
    pill: "border-slate-200 bg-slate-100 text-slate-600",
    dot: "bg-slate-400",
  },
  "Strong research match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-emerald-500",
  },
  "Good research match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-brand-500",
  },
  "Potential match": {
    pill: "border-accent-200 bg-accent-50 text-accent-700",
    dot: "bg-amber-500",
  },
};

export function outreachLabel(status: OutreachStatus): string {
  return OUTREACH_STATUS_META[status].label;
}
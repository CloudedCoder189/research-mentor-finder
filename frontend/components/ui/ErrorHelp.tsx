import Link from "next/link";

export function ErrorHelp() {
  return (
    <p className="mt-2 text-sm text-slate-500">
      Try again shortly. If the problem continues,{" "}
      <Link href="/contact" className="focus-ring rounded-control text-brand-700 underline">
        contact support
      </Link>.
    </p>
  );
}

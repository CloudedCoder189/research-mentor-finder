import { cn } from "@/lib/cn";

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("card", className)}>{children}</div>;
}
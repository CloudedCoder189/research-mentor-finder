export function initials(name: string): string {
  return name
    .replace(/[^A-Za-z' \-.]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function firstName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[0] ?? name;
}

export function formatDate(value: string): string {
  if (!value) return "Not set";
  return value;
}

export function formatSentDate(value: string): string {
  if (!value) return "Not sent";
  return value;
}
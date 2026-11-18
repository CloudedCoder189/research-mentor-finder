import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  return (
    <button
      type="button"
      data-theme-toggle
      className="theme-toggle"
    >
      <span className="theme-toggle-track" aria-hidden="true">
        <span className="theme-toggle-thumb" />
        <Sun className="theme-toggle-sun" />
        <Moon className="theme-toggle-moon" />
      </span>
      <span className="theme-toggle-label theme-light-label">Dark mode</span>
      <span className="theme-toggle-label theme-dark-label">Light mode</span>
    </button>
  );
}

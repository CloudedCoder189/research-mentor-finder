/** Clear temporary, tab-scoped drafts when account access ends. */
import { clearComparisonSelection } from "@/lib/comparisonSelection";

export function clearDraftRecovery() {
  clearComparisonSelection();
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith("rmf-unsaved-draft:") || key.startsWith("rmf-comparison:")) window.sessionStorage.removeItem(key);
    }
  } catch { /* Storage may be unavailable. */ }
}

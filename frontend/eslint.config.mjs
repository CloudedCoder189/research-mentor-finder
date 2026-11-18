import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    // Keep tested external-load/account-reset flows during this migration.
    // Their synchronous loading resets are intentional; compiler adoption and
    // derived-state refactoring are separate work. Other hooks rules stay on.
    files: [
      "app/outreach/page.tsx", "components/auth/SignInPrompt.tsx",
      "components/outreach/Composer.tsx", "components/researcher/WhyMatchPanel.tsx",
      "components/researcher/profile/ProfilePageView.tsx", "components/saved/SavedProvider.tsx",
      "lib/auth-context.tsx", "lib/use-dev-tools.ts", "lib/useStudentProfile.ts",
    ],
    rules: { "react-hooks/set-state-in-effect": "off" },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

# Historical Windows prototype tools

These PowerShell scripts supported isolated development, integration testing,
and controlled migration steps for an earlier local prototype. They are preserved
for reference, not for the current public installation or deployment.

For the current application, follow the [main README](../../README.md).
Several scripts below expect private `test-runtime/` and `evidence/` files
that are deliberately **not** included in the public repository.

The scripts now resolve the repository root two directories above this folder.
They were moved together to preserve their relative references to each other.
No live services, accounts, or databases should be operated on with these scripts
without independently reviewing their side effects and prerequisites.

- `Start-LocalPrototype.ps1`, `Start-UpgradedFrontend.ps1` and
  `Restart-HardenedApi.ps1`: isolated prototype service management.
- `Stop-ManagedPrototype.ps1` and `Stop-ReviewedPrototype.ps1`: stop and
  checkpoint isolated prototype services.
- `Activate-AccountLifecycle.ps1` and `Promote-FrontendUpgrade.ps1`:
  historical local promotion steps with dated evidence requirements.
- `Restore-ManagedBackup.ps1`: historical isolated-backup restoration.

Do not run these against a production database or server.

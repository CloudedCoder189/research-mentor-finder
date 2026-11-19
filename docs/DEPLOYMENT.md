# Safe deployment packaging

The public GitHub checkout is **not** a production Docker build context.
The root `.dockerignore` intentionally excludes everything: a direct
`docker build -f deploy/pilot/Dockerfile .` is unsupported and must fail
rather than upload private workspace files to the Docker builder.

The hosted app uses a **separate, generated staging directory** under
`test-runtime/`. Never commit, publish, or zip an entire working folder
or the private runtime database.

## Deployment preparation (operator only)

1. Start with a reviewed researcher source database. The public-only export
   copies an allowlisted set of **researcher columns**; it excludes account,
   session, outreach, and token tables. Review researcher contact data and
   confirm it is appropriate to publish before exporting.
2. The local operator must supply the reviewed deployment inputs
   `deploy/pilot/reviewed-professors.json` and
   `deploy/pilot/link-repairs-20261025.json`. These are deliberately not
   in the open-source repository. Do not substitute private credentials or
   working-directory backups.
3. From a trusted project checkout, run the packaging tool with a source
   database path you have explicitly checked and a **new** staging path:

   ```powershell
   python -m scripts.prepare_pilot_package --source "C:\path\to\reviewed-source.db" --destination "test-runtime/pilot-staging-reviewed"
   ```

4. Inspect the generated `package-manifest.json` and the seed report.
   Only the generated staged folder should be used as the Railway build
   context. Do not deploy this folder until the source dataset, public
   contact information, and operational configuration have been reviewed.
5. The packaging script writes a **default-deny** `.dockerignore` into
   the staging folder. It explicitly re-includes the source files, parent
   directories, and the generated `public-seed.db` and
   `seed-report.json`. Any unrelated file added to the folder remains
   outside Docker's build context.
6. Configure hosting secrets via Railway's private Variables interface.
   Never add filled `.env` files, Google credentials, encryption keys,
   private databases, or private backup archives to the deployment package.

The Dockerfile depends on the generated public seed and report and is not
intended to build directly from GitHub. Local development uses the synthetic
data instructions in the [root README](../README.md).

## What these safeguards do not establish

The exporter has an explicit researcher-field allowlist, and the staging
tool scans known credential formats, but **neither tool can determine
whether individual researcher-field values are appropriate for public
release**. They are not a complete privacy audit, secret scan, or live
deployment verification. The tests validate the generated ignore rules;
they do not execute a real Docker/Railway deployment. A release operator
must review the staged data and check the deployment separately.

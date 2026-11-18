# Google sign-in setup for this local prototype

Live sign-in is now confirmed. The user reached Your account via
`/account?auth=success`; the isolated database contains a Google account and
an unexpired Google session. Original DB fingerprint and all isolated
researcher rows still match the baseline. Evidence is
`evidence/google-signin-2026-10-04/live-success.json`, with personal account
details omitted. Earlier pending-status sections below are historical.

Network recovery: the first live attempt returned `reason=verification`.
Both Google discovery and tokeninfo probes failed with ConnectionError inside
the restricted runtime. Outside it, discovery returned 200 and tokeninfo
returned the expected 400 for an intentionally invalid synthetic token. The
prototype has been restarted outside the restricted runtime with Google mode
enabled, the same isolated DB, and paid AI disabled. The earlier callback did
not log its provider failure stage, so a successful fresh login is still needed
to close verification. See `evidence/google-signin-2026-10-04/network-recovery.json`.

Latest status: the user saved the separate sign-in credentials in the private
working `.env`. The prototype was restarted with `-EnableGoogleSignIn`.
Ten local preflight checks passed: authorization endpoint, configured client,
correct callback, identity-only scopes, matching HttpOnly state cookie, healthy
services, and original DB preservation. Evidence is
`evidence/google-signin-2026-10-04/live-preflight.json`; no credential, cookie or
state values were retained there. Google account consent and the completed
callback/session are still awaiting the user in a regular browser. The initial
setup instructions below document the preceding steps.

The app is prepared at http://localhost:13310 with API http://localhost:18501.
The separate sign-in client is missing. Existing Gmail credentials were detected
in the original project but were neither printed nor copied or changed.

## Google Console step

Use your regular Chrome or Edge browser to sign in at
https://console.cloud.google.com/auth/clients and select the Cloud project that
owns Professor Finder. This task's browser currently shows Google's login screen;
it cannot complete your account login or MFA for you.

Create a **Web application** client named `Professor Finder local sign-in`.
Configure this exact authorized redirect URI:

```
http://localhost:18501/api/auth/callback
```

The app uses a backend redirect, not the JavaScript sign-in widget; an authorized
JavaScript origin is not required for this flow. If configuring one as well, use
`http://localhost:13310`. Do not add Gmail scopes to this sign-in client. The
application requests only `openid`, `email`, and `profile`.

If the consent setup is incomplete, finish Google Auth Platform Branding and
Audience. Keep a prototype in Testing, and add your account to Test users when
the selected audience/testing configuration requires it. Do not publish the
consent screen or enable billing for this step.

Store the new client ID and secret in the **working copy's private `.env`**:

```
AUTH_CLIENT_ID=<new sign-in client ID>
AUTH_CLIENT_SECRET=<new sign-in client secret>
```

Do not paste the secret into chat, evidence files, or `.env.example`. The file is
ignored by the project. Google currently displays new client secrets only at
creation, so save the secret privately when creating the client.

## Prepared local behavior

`Start-LocalPrototype.ps1 -EnableGoogleSignIn` checks for credentials without
printing them, starts against the isolated real-data copy, and supplies:

- AUTH_REDIRECT_URI=http://localhost:18501/api/auth/callback
- AUTH_LOGIN_SUCCESS_URL=http://localhost:13310/account
- Paid AI disabled; no Gmail credentials loaded from the original project.

Stop the currently running prototype before starting another instance. Codex
will handle the restart and acceptance checks when the client is available.
The ordinary launcher still explicitly disables Google credentials by default.

## Validation before live consent

Authentication tests: **42 passed**, one existing dependency deprecation warning.
The first run had two URL-default assertions fail because the initial private
settings file overrode their expected default ports. Those URLs are now supplied
by the launcher, not the private file; the corrected run passed. Both outputs
are retained in `evidence/google-signin-2026-10-04`.

The restarted app's `/api/auth/login` was also checked in the browser: without
credentials it redirects to `http://localhost:13310/account?auth=error&reason=config`
and displays the configuration banner plus the local sign-in button. It no longer
redirects to the original app's port. Backend access logging is disabled in the
prototype launcher so future OAuth codes are not recorded in request URL logs.

The callback now rejects identity tokens for another client, unexpected issuers,
expired/invalid expiries, missing identities and unverified emails. Provider
timeouts or malformed replies produce a sign-in error redirect instead of an
uncaught server exception. A missing secret fails before entering consent.
Tests use mocked Google responses and disposable synthetic databases; they are
not evidence of successful live Google sign-in.

This local implementation retains Google's tokeninfo verification endpoint.
A production release should use the supported Google auth library for local
signature verification; this setup does not certify deployment readiness.

Official references:
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/openid-connect/openid-connect
- https://developers.google.com/workspace/guides/create-credentials

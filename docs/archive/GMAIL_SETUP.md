# Next integration: Gmail drafts

Live integration is now verified. The user completed Gmail consent; one active
Google account has encrypted Gmail credentials with a refresh token. The live
service test created one clearly marked draft addressed only to the connected
account, updated it twice without changing its draft ID, and read back the
correct recipient, subject and body. Local metadata persisted. All nine checks
passed, including original DB and researcher-content preservation. Evidence:
`evidence/gmail-2026-10-04/live-connection.json` and `live-draft-results.json`.

No send operation or mailbox search was performed. The test draft remains in
Gmail and in this account's isolated outreach row for researcher 1126, with
subject `[PROTOTYPE TEST - DO NOT SEND] Gmail draft verification - updated`.
It is addressed to the connected account, not the professor. This was a live
service integration test; HTTP auth and browser draft behavior were tested
separately. Live sent/replied detection and every Gmail UI state remain
unverified. Earlier preparation/pending sections below are historical.

Current status: the user saved the new Gmail callback in Console. The
prototype was restarted outside the restricted runtime with Google and Gmail
enabled. Twelve local preflight checks passed, including the correct Gmail
client/callback/scopes, encrypted isolated pending state, preserved Google
session and unchanged researcher/source DB fingerprints. See
`evidence/gmail-2026-10-04/live-preflight.json`. No real Gmail connection or
draft exists yet; awaiting consent from the user's regular browser.

Google app sign-in is verified. Gmail uses the existing separate web client
named Research Mentor Finder, whose authorized callback is currently
http://localhost:8000/api/gmail/callback.

## One Google Console change needed

Open https://console.cloud.google.com/auth/clients?project=research-mentor-finder-local
in your regular browser. Open **Research Mentor Finder**, the original Gmail
client. Add the following **Authorized redirect URI**, keeping the existing
:8000 URI:

```
http://localhost:18501/api/gmail/callback
```

Save. Do not change the new Professor Finder local sign-in client.

## Local preparation already completed

Offline Gmail checks: **68 passed**, one existing dependency warning. The first
run exposed a test that read the encrypted pending-state file as plain JSON;
it now verifies state roundtrip/consumption through the store for both encrypted
and unencrypted modes. No real Gmail requests occurred in these tests. Both
runs are retained in `evidence/gmail-2026-10-04`.

- Gmail client ID and secret were copied directly from the original private
  settings into the working private .env, without displaying or sharing them.
- The original settings and existing token files were not changed.
- No existing Gmail tokens were copied or reused.
- A private encryption key was prepared for the isolated token store.
- `Start-LocalPrototype.ps1 -EnableGoogleSignIn -EnableGmail` uses the isolated
  researcher DB, token folder `test-runtime/gmail-isolated`, callback :18501,
  return URL http://localhost:13310/outreach, and paid AI disabled.
- Codex will restart the prototype with network access when the Console
  callback is saved. The current running services retain Google sign-in.

You must then complete Gmail consent in your regular browser. The app requests
gmail.compose and gmail.metadata. The compose scope allows draft management
and sending; this task will only create/update a clearly marked test draft,
never send email. Metadata is used for status detection; live mailbox review
is not part of this setup step.

No Gmail connection, real Gmail draft, paid AI call or email send has occurred
during this preparation. These remain separate from the local draft persistence
test that already passed.

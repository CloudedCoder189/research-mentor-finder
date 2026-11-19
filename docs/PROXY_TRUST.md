# Reverse-proxy IP trust for rate limiting

This single-worker pilot runs FastAPI on `127.0.0.1:18501` behind Caddy.
Managed Uvicorn explicitly uses `proxy_headers=False`. Caddy replaces
`X-RMF-Client-IP` in upstream API requests with the `X-Real-IP` header it
received from Railway's public HTTP edge. The backend uses that field only when:

1. The socket peer is loopback;
2. `RATE_LIMIT_TRUST_PILOT_PROXY=1` was explicitly configured;
3. Exactly one `X-RMF-Client-IP` header exists; and
4. Its value is one syntactically valid, globally routable IP address.

Other forwarding headers, duplicate headers, comma-delimited values,
and private/reserved IP addresses are not used. If validation fails,
the rate limiter uses the socket peer; global limits still apply.

## Deployment trust assumption

Railway's published public HTTP ingress is documented as **overwriting**
client-supplied `X-Real-IP` (and other standard forwarding headers).
This upstream sanitization is what makes the Caddy-to-backend header useful
for per-client admission control. **Caddy alone cannot authenticate the origin
of the `X-Real-IP` value.** Railway does not publish stable ingress proxy
source CIDRs or an authenticated forwarding mechanism.

Only expose the Caddy listener via Railway's normal public HTTP edge.
**Do not** expose the same listener through a raw TCP proxy, allow untrusted
services in the same Railway private-network environment to call it, or reuse
the configuration under a different ingress that forwards client-supplied
`X-Real-IP` values unchanged. Those paths do not necessarily sanitize the
header and could permit client-identity spoofing.

The application does not use client IPs for authentication or authorization.
Rate limits remain process-local and would require a shared limiter before
adding replicas or multiple backend workers.

## Validation

- `tests/test_admission.py` checks that only the trusted loopback hop accepts a
  single valid proxy identity, and that malformed and duplicate headers fall
  back to the socket peer.
- It checks that both pilot Caddyfiles overwrite `X-RMF-Client-IP` before
  forwarding requests to the API.
- Before changing the hosting topology, independently verify the new provider's
  forwarding-header contract or disable `RATE_LIMIT_TRUST_PILOT_PROXY` until a
  verified trusted proxy is configured.

Relevant sources:

- [Railway public ingress technical specifications](https://docs.railway.com/networking/public-networking/specs-and-limits#technical-specifications)
- [Railway support: HTTP edge header replacement and private networking caveats](https://station.railway.com/questions/official-x-real-ip-trust-guarantees-for-baaf8ac9)
- [Caddy reverse proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)

# Security

## ACTION REQUIRED: exposed credentials

On 2026-09-04 the following credentials were found hardcoded in `Dockerfile`
(lines 25-35) and committed to a **public** GitHub repository
(`github.com/joshitachu/mvp`, `"visibility": "public"` confirmed via the GitHub
API). They were introduced in commit `de8b5e7` *"Add environment variables to
Dockerfile for VM deployment"*.

They have been removed from the working tree, but **removal from a file does not
remove them from git history**. Anyone who has cloned or can clone the repo still
has them. Assume they are compromised.

### Rotate these, in this order

| Priority | Credential | Where to rotate | Notes |
|---|---|---|---|
| 1 | `DATABASE_URL` password (`voetbal123`) | Postgres / Supabase | Full read-write DB access. Highest impact |
| 2 | `API_PASSWORD` (TenderNed, user `TNXML08248`) | TenderNed — `functioneelbeheer@tenderned.nl` | **STOP — read the warning below before touching this one** |
| 3 | `GROQ_API_KEY` | console.groq.com | Billable |
| 4 | `GOOGLE_API_KEY` | console.cloud.google.com | Billable |
| 5 | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` | console.cloud.google.com / programmablesearchengine.google.com | Billable |
| 6 | `SERPAPI_API_KEY` | serpapi.com | Billable |
| 7 | `OPEN_ROUTER` | openrouter.ai | No code currently reads this — consider dropping it entirely |

Check the billing/usage dashboard on each of 3-7 for unexpected activity before
rotating, so you know whether anything was actually abused.

### ⚠️ Do not rotate the TenderNed credential without a reissue commitment first

Verified 2026-09-04 against the live API:

| Endpoint | No credentials | With our credentials |
|---|---|---|
| `/v2/publicaties` (list) | **200** — 145,300 publications | 200 |
| `/v2/publicaties/{id}/public-xml` (detail) | **403** | **200** |

So the credential is *not* needed for discovery, but it **is** the only way we get
the structured per-notice XML — winner, contract value, dates. That is the entire
enrichment pipeline.

TenderNed is reported to have **suspended new XML API credential applications**
("nieuwe aanvragen tot de XML API worden voorlopig niet verwerkt"), with a
waiting list of several months. I have not independently confirmed that this is
still current — **verify it before you act**.

The risk is asymmetric: if you revoke this credential and reissue turns out to be
slow, the structured pipeline is dead for months and there is no workaround
inside TenderNed. Sequence it as:

1. Contact `functioneelbeheer@tenderned.nl` and get the reissue turnaround **in writing**.
2. Only then rotate.
3. Meanwhile, assume the credential is compromised and monitor for unexpected use.

Rotating the other six keys carries no such dependency — do those immediately.

Longer term this dependency should be removed anyway: the free, unauthenticated
**TED v3 API** carries richer structured data (lots, award-criterion weights, bidder
counts) than TenderNed's XML, joined via the `pbNummerTed` field. See the Phase 2
plan.

### Purging git history

Not done — it rewrites published history and force-pushes, which breaks every
existing clone. That is your call, not something to do unilaterally.

If you want it, the options are `git filter-repo` (recommended) or BFG:

```bash
git filter-repo --path Dockerfile --invert-paths --force   # nukes the file from all history
# then re-add a clean Dockerfile, and force-push
```

Rotating the keys is the part that actually protects you. History purging only
reduces future discoverability of already-compromised values — do the rotation
first, and do not treat the purge as a substitute for it.

## Secret handling going forward

- Secrets come from the runtime environment, never from the image or the repo.
- `.env` is gitignored. Keep it that way; verify with `git check-ignore -v .env`.
- Supply production values via `--env-file` or your orchestrator's secret store.
- Consider a pre-commit secret scanner (`gitleaks`, `trufflehog`) in CI.

## Known remaining issues

These are tracked but not yet fixed.

### Authentication is a self-service 12-digit code

`POST /auth/request-code` is unauthenticated by design and mints a valid
credential to any caller (`server.py:1410`). There is no user identity, no
expiry, no roles, and no revocation — possession of a 12-digit code is the
entire access model, and anyone can mint one on demand.

For the current internal-only deployment behind a trusted network this is a
known, accepted limitation. It is **not** adequate if the service is ever exposed
publicly or sold to clients. Fixing it properly means choosing a real auth model
(SSO/OIDC), which is a product decision rather than a bug fix.

### Rate limiter is per-process and trusts a client header

`RateLimiter` (`server.py:57-85`) keys on the `CF-Connecting-IP` request header,
which a client can set freely unless Cloudflare is the only ingress path. It also
stores state in a process-local dict, so it does not hold across multiple uvicorn
workers, and it never evicts empty keys (unbounded memory growth).

Additionally it raises `HTTPException` from inside a `BaseHTTPMiddleware`, which
is outside Starlette's exception-handling middleware — so a rate-limited request
surfaces as a **500, not a 429**.

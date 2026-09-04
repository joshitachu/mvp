# Ithaka — project status & roadmap

**Last updated:** 2026-09-04
**Scope:** backend `joshitachu/mvp` (this repo) + frontend `joshitachu/ithaka`

---

## 1. The goal

Turn this from a working prototype into a reliable **tender-intelligence platform** for
internal consultancy use, serving four jobs:

| Job | What the user asks | Data needed |
|---|---|---|
| **Lead generation** | "Which companies just won public contracts, and are they worth approaching?" | Award notices + winner enrichment |
| **Bid intelligence** | "Which open tenders match our profile, and when do they close?" | Contract notices + deadlines + CPV matching |
| **Market analysis** | "Who wins what, from which buyers, at what price — and when does that contract come up again?" | Historical depth + contract durations |
| **SROI assessment** | "Does this supplier deliver social return?" | Tender documents + supplier evidence |

Non-goals for now: this is an **internal tool**. No SSO, no billing, no hard
multi-tenancy. Data isolation still matters (client-confidential procurement data,
multiple colleagues), so owner scoping is enforced — but we are not building SaaS
infrastructure.

**Working principle:** fix foundations before features. Every claim in this document
was verified against live data or the running system; nothing here is inferred.

---

## 2. Current state

### Running locally

```bash
# backend  (this repo)
cd ~/Documents/ithaka     && .venv/bin/uvicorn server:app --port 8010 --reload

# frontend (joshitachu/ithaka)
cd ~/Documents/ithaka-ui  && npm run dev        # :3000
```

Login at http://localhost:3000 → **"Code" tab** → a 12-digit code.
Mint one with `curl -X POST http://127.0.0.1:8010/auth/request-code`.
The Account/username-password tab does not work — it calls `/auth/login`, which the
backend does not implement.

Port 8010 rather than 8000 because Docker occupies 8000/8001 on the dev machine.

### Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL 16. 25 endpoints.
- **Frontend:** Next.js 16 App Router. Every route handler proxies to `BACKEND_URL`.
- **Data source:** TenderNed TNS API. 145,300 publications, no auth on the list
  endpoint; the per-notice XML endpoint requires HTTP Basic.

---

## 3. What was done

### 3.0 Integration fixes (frontend ↔ backend)

The two repos disagreed about the API contract, so the entire CRM page was dead.

| Bug | Detail |
|---|---|
| Wrong paths | UI called `/api/companies/*`; backend serves `/crm/companies/*` → 404 on every CRM call |
| Missing auth header | None of the 4 CRM route handlers forwarded `X-User-Code`, which the backend requires — so fixing the paths alone would have turned 404s into 422s |
| Typo | `process.env.BACKEND_UL` (missing `R`) → that route ignored the env var entirely |
| Excel export 500 | `_make_excel_response` passed tz-aware `TIMESTAMPTZ` values to openpyxl, which rejects them |

Audited all 20 UI route handlers for the missing-header defect; it was confined to
those 4. Extracted `lib/backend.ts` (in the UI repo) so a new route cannot forget it.

**Verified:** full CRM CRUD works end-to-end through the UI proxy; Excel export
downloads a valid 72×34 workbook.

### 3.1 Phase 0 — stop the bleeding ✅

**Critical: cross-user data loss.** `notices.notice_id` carried a *global* unique
constraint, and the upsert did `ON CONFLICT (notice_id) DO UPDATE SET import_id =
excluded.import_id, owner_code = excluded.owner_code`. Any second user importing an
overlapping date range silently re-parented every shared notice to themselves.

Reproduced before fixing:

```
BEFORE   import A / owner 3953…  →  71 notices
         (user B imports the same 2 days)
AFTER    import B / owner 1111…  →  71 notices
         import A                →   0 notices     ← silently emptied
         …while still reporting total_records = 71
```

Fixed by `migrations/001_fix_notice_uniqueness.sql` → `UNIQUE (import_id, notice_id)`
plus the matching conflict target in `server.py`. **Verified** with a real second
import: A kept all 71 rows.

**Other Phase 0 items:**

| Fix | Verification |
|---|---|
| 3 hot-path indexes (`migrations/002`) — every read on `(import_id, owner_code)` was a seq scan | Index scans confirmed via `enable_seqscan=off` |
| Auth added to `/api/search/company` and `/imports/{id}/sroi-download` — both were fully unauthenticated | 422 without header, 200 with |
| 6 `async def` handlers doing blocking DB/HTTP work → `def` | 20 routes resolve; optional-body contract preserved |
| Secrets removed from `Dockerfile` | 6 secret patterns, 0 hits in working tree |

Endpoint auth audit: **20/25 now require auth.** The 5 open ones are correct by
design (`/health`, `/validate-code`, `/auth/request-code`, `/regions`, `/crm/init`).

### 3.2 Phase 1 — retrieval (partly done)

**Performance: 64.7s → 5.7s on an identical import. 11.3× faster.**

Root cause was not the API — it was that every request used a bare `requests.get()`,
building and discarding a Session, so each of N per-notice fetches paid a fresh
TCP+TLS handshake. Measured over the same 6 URLs: 0.890s → 0.268s with keep-alive.

- Pooled `requests.Session` with `Retry(total=3, backoff_factor=0.5,
  status_forcelist=[429,5xx], respect_retry_after_header=True)` — there was
  previously **no retry logic anywhere**
- 8-way concurrent XML fetch (`TN_FETCH_WORKERS`), order preserved
- Split `(connect, read)` timeouts so a hung connect can't stall an import

**Silent data loss closed.** Every HTTP or parse failure was a bare `continue`, so an
import could store 40 of 71 notices and report success. Now counted and returned:
`{"listed":100,"fetched":100,"http_failed":0,"parse_failed":0,"complete":true}`.

**Import lifecycle** (`migrations/003`): `pending → running → completed | partial |
failed`, with `error_message`, `started_at`/`finished_at` and the counters persisted.
`partial` is new and matters — it distinguishes a truncated import from a successful
one, which was previously impossible. Failure path unit-tested with a patched
outage: status `failed`, error captured, exception re-raised, no orphan row.

**Publication-type classification** (`publication_types.py`, `migrations/004`).
This was filed as "add announcement types" but turned out to be a correctness bug.

The app filtered on TenderNed's coarse `typePublicatie == "AGO"` and treated
everything returned as an award. Measured over 300 live AGO records:

| | share | has winner |
|---|---|---|
| genuine awards (`EF29/30/31/32/33`, `EFE4`) | 84.3% | yes |
| **VEAT** (`EF25/26/28`) — *intent* to award without competition | 6.7% | **no winner yet** |
| **cancelled** procedures | 9.0% | **0 of 7** |

So ~16% of stored "awards" were not awards. VEAT rows in particular were feeding
winner-based lead-gen and SROI targeting with notices that have no awardee.

Also verified against the live API:
- Authoritative enum is `[VAK, AAO, AGO, REC, MAC, VBE, AAW]`
- **`publicatieType=VBE` is broken server-side** — returns all 145,300 records
  unfiltered. Cancellations must be detected via the `isVroegtijdigeBeeindiging`
  booleans instead.
- CPV filters require the check digit (`72000000-5` works, `72000000` is ignored)
- Unknown query params are **silently ignored**, not rejected
- There is no free-text search parameter

---

## 4. Verified defects still open

Evidence-backed, not yet fixed. Roughly in priority order.

| # | Defect | Evidence |
|---|---|---|
| 1 | `POST /imports` still synchronous — holds a request, threadpool slot and DB connection for the whole fetch | Less urgent at 11× (a year is now ~17 min, was 3.1 h) |
| 2 | Cache serves **partial results as success**. Identical request returned 71 records, then 39. Coverage is a global `min/max(Publicatiedatum)` with no gap detection | Reproduced live |
| 3 | `_search_companies_in_db` reads `tenderned_raw`, which **no code writes**. "Previous tenders by this winner" always returns empty | 0/71 rows flagged |
| 4 | Cache rows have every Dutch-named column NULL (71/71). A cache *hit* returns notices with no URL and no publication date | Live query |
| 5 | CPV cache can never hit — writer omits `cpv_code`, reader filters on it | `tenderned_raw_cpv_cached` = 0 rows, ever |
| 6 | **Per-notice CPV is never stored.** `notices` has no CPV column. This is the primary lead-matching dimension | Schema |
| 7 | Province wrong on ~40% of rows — matches *woonplaats* against a *gemeente* list. Fix: derive from `win_postcode` | 43/71 resolved |
| 8 | `notices.region` populated on 0 rows despite being an exposed filter | Live query |
| 9 | LLM never sees the pages the crawler finds — `sroi_scanner.py:743` builds ~96k chars, `:388` sends `[:8000]` | Code |
| 10 | No verification that a scraped site belongs to the right company — takes Google result #1 | Code |
| 11 | LLM failure silently degrades to a keyword score on a **different scale**, written to the same column, then averaged | `:307` (0–10) vs `:399` (0–100) |
| 12 | `sroi_ai_utils.py` is dead code (0 importers, 293 lines) — and contains the *better* design | grep |
| 13 | Auth is a self-service 12-digit code. `/auth/request-code` is unauthenticated and mints credentials on demand. No identity, expiry, roles or revocation | Accepted for internal use; see `SECURITY.md` |

---

## 5. Roadmap

### Phase 1 (remainder)
- ✅ Async job submission: `POST /imports` now returns `202 + import_id` after
  persisting a `pending` job. The TenderNed work runs after the response with a
  worker-owned database session; `GET /imports` is the status endpoint and the
  UI refreshes it every two seconds while a job is active.
- ✅ Crash recovery: on startup, previously `running` imports are marked
  `failed` with an explicit restart message. They can no longer appear to run
  forever after a deploy or crash.

### Phase 2 — data model & caching
- ✅ **Immutable raw layer:** migration `005_canonical_tender_data.sql` adds
  `tender_notices`, preserving both the TenderNed listing object and source XML.
  New API-fetched imports write it before their UI projection is saved.
- ✅ **CPV table:** `tender_notice_cpvs` stores one code per notice; the legacy
  CPV-cache writer is also populated correctly during the transition.
- ✅ **Company entity:** `tender_companies` is keyed by KVK where present, with a
  normalized name/location fallback. Historic-company search prefers it and only
  falls back to the legacy table for data not yet backfilled.
- ✅ **Lot-level grain:** eForms `LotResult` / `ProcurementProjectLot` records are
  persisted in `tender_notice_lots` when present. No synthetic lot is created.
- ✅ Province now uses known city mapping first and a postcode fallback.
- Remaining: apply migrations, backfill the historical cache tables into the
  canonical layer, then remove legacy cache reads in a separately reviewed change.

### Phase 3 — AI / SROI pipeline
Current output is **not defensible as a compliance verdict**: no source citation, no
company verification, LLM and keyword verdicts indistinguishable, and the rubric's
`TRUE = score > 20` on a deliberately "mild" scale means nearly every corporate
homepage passes.

- ✅ Reject search results that do not identify the target company before scraping.
  KVK verification still requires an approved KVK-data integration.
- ✅ Send relevance-ranked chunks, not `[:8000]` off the top.
- Structured output + schema validation + bounded retry
- ✅ Evidence is checked against the submitted source text; unsupported model
  output becomes `insufficient_evidence`. Keyword fallback is explicitly marked
  as such rather than presented as an AI compliance verdict (`migration 006`).
- Per-company cache (large suppliers recur constantly)
- Target: 500 notices in ~20 min, vs 8–21 h today

### Phase 4 — UI
Rebuild on the new API: server components, real tables (sort/filter/paginate), saved
searches, job progress, evidence display.

### Phase 5 — features
CPV alerting, contract-expiry / re-tender tracking, buyer spend profiles, competitor
win/loss analysis.

---

## 6. Source architecture (researched, not yet built)

| Layer | Source | Why |
|---|---|---|
| Primary NL feed | TenderNed TNS API | **CC0 licence**, same-day, no auth on list, includes below-threshold notices |
| Structured detail | **TED v3 API** (free, unauthenticated), joined via `pbNummerTed` | Lot-level data, award-criterion weights, bidder counts by SME/size band, lowest/highest tender values |
| Bulk history | TED daily packages (~17 MB/day, no auth) | Cheaper than paginating the API for backfill |
| Company enrichment | KVK Basisprofiel — €0.02/query, €6.40/month | Name/address/SBI verification. Free CC BY 4.0 HVD bulk dataset for BV/NV attributes |

**Strategic note:** TED carries richer structured data than TenderNed's XML and needs
no credentials. Moving enrichment to TED removes the dependency described in §7.

### Known-dark areas — state these to users, don't paper over them
- **Framework call-offs are never published** (art. 2.135 Aw). 33% of publications
  are frameworks (`aardVanDeOpdracht=RAA`); their actual spend allocation is invisible.
- **Meervoudig/enkelvoudig onderhandse** procedures below threshold have no
  publication duty at all.
- Whether renewal options were exercised, and framework ceiling consumption.
- ~33% of tenders run on third-party platforms (Mercell etc.) where documents live
  off-TenderNed.

---

## 7. Action required (not code — needs a human)

1. **Rotate the exposed credentials.** The repo is **public** (confirmed via the
   GitHub API) and live keys sit in commit `de8b5e7`. See `SECURITY.md` for the
   ordered runbook.

2. **⚠️ Do NOT rotate the TenderNed credential first.** Verified: `public-xml`
   returns **403 without credentials, 200 with**. It is the only route to structured
   per-notice data. TenderNed is reported to have suspended new XML API credential
   applications with a months-long waiting list — verify before acting. Get a reissue
   turnaround in writing, *then* rotate. The other six keys have no such dependency.

3. **Git history purge** — not done. It force-pushes over published commits and
   breaks every clone. Your call. Rotation is what actually protects you.

---

## 8. Open decisions

- **Do you have the 2016–2024 historical dataset?** The Excel file is gitignored.
  Market analysis and "has this company won before" both depend on it. If not, we
  backfill from the API.
- **SROI: signal or verdict?** I previously suggested reading the eForms
  `BT-775 Social Procurement` flag instead of scraping websites. **That was wrong** —
  measured fill rate across all Dutch notices in the last 30 days (n=1,758):
  `soc-obj` on 14 notices (0.8%), `BT-775 = opp` on exactly **1**. The structured
  field is unusable as an SROI detector. SROI requirements live in the tender
  documents (PDF leidraad), so a defensible verdict needs a document-parsing
  pipeline — more work than previously scoped.
- **Prototype TED daily ingest?** It unlocks bidder counts, price spreads and
  contract-expiry tracking, and can be proved on one day's file.

---

## 9. Files added/changed

**This repo:**
```
PROJECT_STATUS.md          this file
SECURITY.md                credential exposure + rotation runbook
publication_types.py       TenderNed classification (verified against live API)
migrations/001_fix_notice_uniqueness.sql
migrations/002_add_hot_path_indexes.sql
migrations/003_import_status.sql
migrations/004_notice_classification.sql
server.py                  auth, status lifecycle, classification, Excel fix
final_tenderned.py         session pooling, retries, concurrency, counters
models.py                  constraints, indexes, new columns
Dockerfile                 secrets removed
```

**Frontend repo (`joshitachu/ithaka`):**
```
lib/backend.ts             new — shared BACKEND_URL + auth header forwarding
app/api/crm/**             4 route handlers: paths, auth header, typo
```

Migrations are plain SQL (no Alembic in this project), idempotent, and each carries
the reasoning and the evidence in a header comment. Apply with:

```bash
psql -d supabase_subset -v ON_ERROR_STOP=1 -f migrations/00N_*.sql
```

**Nothing is committed** — all changes are in the working tree for review.

---

## 10. Test status

Backend regression: **12/12**. UI proxy routes: **3/3**.
No automated test suite exists in either repo — these are curl-based smoke checks.
Building a real test suite should precede Phase 2's schema rewrite.

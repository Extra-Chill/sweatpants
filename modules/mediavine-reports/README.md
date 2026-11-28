# mediavine-reports

Automates pulling **per-period, per-URL Mediavine revenue** via sweatpants'
pooled, proxied Playwright browser, and POSTs the rows back to a receiver
(e.g. `extrachill-analytics`) using an HMAC-signed callback.

## Why a browser module

Mediavine has **no reporting API** (confirmed 2026-06-21) — no GraphQL, no
public endpoint, no reusable credential. The only data-out path is the
reporting dashboard itself: its CSV export, or the JSON its SPA frontend
fetches over XHR. That makes this a browser-automation problem — exactly what
sweatpants (pooled, proxied, retryable, checkpointed Playwright) is built for.

Keeping it on sweatpants (chubes.net) — **not** baked into a WordPress plugin —
means EC prod stays clean (no Playwright/scraper deps) and the fragility of an
undocumented dashboard is isolated in the tool designed to absorb it.

## Architecture

```
extrachill-analytics (EC prod) --signed job request--> sweatpants @ chubes.net
                                                        mediavine-reports module
                                                        (Playwright -> reporting.mediavine.com)
                               <--HMAC-signed callback (revenue rows)--+
```

The WP glue (companion: `extrachill-analytics#65`) mints a signed sweatpants
job-request token, POSTs to the chubes.net `/jobs` endpoint, then receives the
HMAC-signed callback and feeds the rows into the existing
`extrachill analytics revenue import` path (period-keyed). The revenue store +
import logic already exist — this module only **feeds** them; it does not
reimplement revenue parsing/rollup.

## Inputs

| input | required | description |
|-------|----------|-------------|
| `periods` | one of | JSON list of `{period, period_start, period_end}` (YYYY-MM-DD). Use for multi-bucket backfill. Wins over the single-period inputs. |
| `period_start` / `period_end` | one of | A single reporting period (YYYY-MM-DD). |
| `period` | no | Label for the single-period case. Defaults to `<start>..<end>`. |
| `report_type` | no | Only `pages` (per-URL revenue) is implemented. Default `pages`. |
| `callback_url` | no | HTTPS receiver for the completed revenue rows. |
| `callback_secret` | no | Shared HMAC secret. Signs the callback (sweatpants core format → `wp_native_auth_verify_external_token`). |
| `callback_issuer` | no | `iss` claim. Default `sweatpants`. |
| `callback_user_id` | no | `sub` claim — the receiving WP user_id. |

## Settings (secrets — stay on sweatpants, never on WP)

| setting | required | description |
|---------|----------|-------------|
| `mediavine_email` | yes | Dashboard login email. |
| `mediavine_password` | yes | Dashboard login password. |

## Output / callback shape

Each completed period yields incrementally, and on completion the module POSTs:

```json
{
  "job_id": "<sweatpants job id>",
  "status": "complete",
  "report_type": "pages",
  "period_count": 5,
  "total_rows": 1234,
  "periods": [
    {
      "period": "2022",
      "period_start": "2022-01-01",
      "period_end": "2022-12-31",
      "report_type": "pages",
      "row_count": 247,
      "rows": [
        {"slug": "/some-post", "views": 10000, "revenue": 123.45, "rpm": 12.3, "period": "2022"}
      ]
    }
  ]
}
```

Row shape (`slug`, `views`, `revenue`, `rpm`, `period`) matches what the
`extrachill analytics revenue import` path expects.

## Resume / checkpointing

The module checkpoints `completed_periods` after each period, so a multi-bucket
backfill resumes after a restart without re-pulling finished periods.

## ⚠️ Fragility — the dashboard layer needs a live capture

Mediavine **rebuilt its reporting dashboard in April 2026**. The dashboard
interaction — login selectors, the pages-report URL, the date-range controls,
and the export/XHR endpoint — is the fragile part and is **isolated** in two
methods in `main.py`:

- `_login()` — the login flow.
- `_scrape_period()` — the single swappable scrape strategy (currently outlines
  the **preferred CSV-export path**; XHR-JSON is the documented fallback).

Every selector/endpoint in those methods is marked `# TODO(confirm)` because it
**cannot be verified from the build environment** (no Mediavine credentials
here). Before a real run:

1. Log into the live dashboard manually with DevTools open.
2. Capture the login form selectors, the pages-report URL + date-range control,
   and the export trigger / XHR endpoint in the Network tab.
3. Fill in the `TODO(confirm)` markers.

`_scrape_period()` **raises a clear, actionable error rather than fabricating
rows** when the export flow fails — a run cannot silently produce empty or
made-up revenue. Fix the fragile layer; don't mask it.

## Operating guidance

- This automates **our own** dashboard login to export **our own** revenue —
  far more defensible than hammering an undocumented public API. Keep it **low
  frequency** (a backfill run, then monthly), our account only. Be mindful of ToS.
- First milestone: a **backfill** pulling yearly buckets 2022→2026 (5 periods) —
  that alone draws the revenue curve (2022 peak → Sept-2023 HCU cliff → now).
  Monthly granularity around the 2023 cliff is a follow-up.

## Dependencies

Depends on **sweatpants#26** — the signed-callback SENDER is a core SDK
primitive (`Module.send_signed_callback`). This module does not hand-roll HMAC.

No module-specific runtime deps; uses the stdlib + sweatpants core (Playwright
is a core sweatpants dependency).

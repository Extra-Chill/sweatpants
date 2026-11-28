"""Mediavine Revenue Reports module for Sweatpants.

Automates pulling per-period, per-URL revenue from the Mediavine reporting
dashboard using sweatpants' pooled, proxied Playwright browser. Mediavine has
NO reporting API (confirmed 2026-06-21) — the only data-out path is the
dashboard itself (CSV export or the JSON its SPA frontend XHRs). That makes
this a browser-automation problem, which is exactly what sweatpants is for.

Architecture (chubes.net runs sweatpants — NOT EC prod):

    extrachill-analytics (EC prod) --signed job request--> sweatpants @ chubes.net
                                                            mediavine-reports module
                                                            (Playwright -> reporting.mediavine.com)
                                   <--HMAC-signed callback (revenue rows)--+

EC prod stays clean (no Playwright/scraper deps); chubes.net does the browser
automation; results return via the proven signed-callback pattern.

Depends on sweatpants#26: the signed-callback SENDER is now a core SDK
primitive (`Module.send_signed_callback`) — this module does NOT hand-roll
HMAC, it calls the shared primitive.

============================================================================
FRAGILITY NOTICE — READ BEFORE TRUSTING THE NUMBERS
============================================================================
Mediavine rebuilt its reporting dashboard in April 2026. The dashboard
interaction — login selectors, the report URL, the date-range controls, and
the export/XHR endpoint — is the FRAGILE part and is intentionally isolated in
two methods: `_login()` and `_scrape_period()`. The selectors/endpoints below
are marked `# TODO(confirm)` because they CANNOT be verified from this
environment (no Mediavine credentials here). Before a real run, capture a
manual session against the live dashboard (DevTools Network tab), confirm the
exact selectors + the export/XHR endpoint, and fill them in. Do NOT trust a
run until those TODOs are resolved against the live dashboard.
============================================================================
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from typing import Any, AsyncIterator, Optional

from sweatpants import Module, get_browser


# Mediavine reporting surface (April-2026 rebuild). Hostnames are stable enough
# to hardcode; the per-page selectors/endpoints below them are NOT and are
# marked TODO(confirm).
LOGIN_URL = "https://publisher-identity.mediavine.com/login"  # TODO(confirm) exact login route
REPORTS_BASE_URL = "https://reporting.mediavine.com"  # TODO(confirm) reports app origin

# Per-request navigation timeout (ms). Dashboard SPA can be slow to hydrate.
NAV_TIMEOUT_MS = 60_000


class MediavineReports(Module):
    """Pull per-period Mediavine revenue rows via Playwright and callback the result."""

    async def run(
        self, inputs: dict[str, Any], settings: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute the revenue pull.

        Args:
            inputs: periods | (period_start, period_end[, period]), report_type,
                callback_url, callback_secret, callback_issuer, callback_user_id
            settings: mediavine_email, mediavine_password
        """
        report_type = inputs.get("report_type", "pages")
        if report_type != "pages":
            raise ValueError(
                f"report_type {report_type!r} is not implemented; only 'pages' is supported"
            )

        periods = self._normalize_periods(inputs)
        if not periods:
            raise ValueError(
                "Provide either `periods` (a list) or both `period_start` and `period_end`"
            )

        email = settings.get("mediavine_email")
        password = settings.get("mediavine_password")
        if not email or not password:
            raise ValueError(
                "mediavine_email and mediavine_password settings are required"
            )

        callback_url = inputs.get("callback_url")
        callback_secret = inputs.get("callback_secret")
        callback_issuer = inputs.get("callback_issuer", "sweatpants")
        callback_user_id = inputs.get("callback_user_id")

        # Resume support: skip periods already completed in a prior run.
        completed = set(self.get_checkpoint("completed_periods", []) or [])

        await self.log(
            f"Mediavine revenue pull: {len(periods)} period(s), report_type={report_type}"
        )
        await self.save_checkpoint(
            stage="started",
            report_type=report_type,
            total_periods=len(periods),
        )

        collected: list[dict[str, Any]] = []

        # use_proxy=True keeps us behind the pooled residential proxy. This is
        # OUR OWN dashboard login to OUR OWN account — low frequency, ToS-mindful.
        async with get_browser() as browser:
            page = await browser.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)

            await self._login(page, email, password)

            for spec in periods:
                label = spec["period"]
                if label in completed:
                    await self.log(f"Skipping already-completed period: {label}")
                    continue

                await self.log(
                    f"Pulling period {label} "
                    f"({spec['period_start']} → {spec['period_end']})"
                )

                rows = await self._scrape_period(
                    page,
                    period_start=spec["period_start"],
                    period_end=spec["period_end"],
                )

                # Tag every row with its period so the receiver can key on it.
                for row in rows:
                    row["period"] = label

                period_result = {
                    "period": label,
                    "period_start": spec["period_start"],
                    "period_end": spec["period_end"],
                    "report_type": report_type,
                    "rows": rows,
                    "row_count": len(rows),
                }
                collected.append(period_result)

                # Yield incrementally so a multi-month pull surfaces progress and
                # checkpoint so a restart resumes after the last completed period.
                completed.add(label)
                await self.save_checkpoint(
                    stage="period_complete",
                    completed_periods=sorted(completed),
                    last_period=label,
                )
                yield {
                    "status": "period_complete",
                    "period": label,
                    "row_count": len(rows),
                    "rows": rows,
                }

        final_result = {
            "status": "complete",
            "report_type": report_type,
            "periods": collected,
            "period_count": len(collected),
            "total_rows": sum(p["row_count"] for p in collected),
        }
        await self.save_checkpoint(stage="complete")
        yield final_result

        # Fire the completion callback (best-effort) via the core SDK primitive
        # (sweatpants#26). Signing + delivery + job_id injection live in core;
        # this module does NOT hand-roll the HMAC POST.
        if callback_url:
            await self.send_signed_callback(
                callback_url,
                final_result,
                callback_secret,
                issuer=callback_issuer,
                user_id=callback_user_id,
            )

    # -----------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------

    @staticmethod
    def _normalize_periods(inputs: dict[str, Any]) -> list[dict[str, str]]:
        """Normalize inputs into a list of {period, period_start, period_end}.

        Accepts either a `periods` list (each item a dict with period_start +
        period_end and an optional period label) or a single
        period_start/period_end pair. The `periods` form wins when both are set.
        """
        raw = inputs.get("periods")
        if raw:
            if isinstance(raw, str):
                # Inputs may arrive JSON-encoded depending on the transport.
                raw = json.loads(raw)
            normalized: list[dict[str, str]] = []
            for item in raw:
                start = item["period_start"]
                end = item["period_end"]
                label = item.get("period") or f"{start}..{end}"
                normalized.append(
                    {"period": label, "period_start": start, "period_end": end}
                )
            return normalized

        start = inputs.get("period_start")
        end = inputs.get("period_end")
        if start and end:
            label = inputs.get("period") or f"{start}..{end}"
            return [{"period": label, "period_start": start, "period_end": end}]

        return []

    # -----------------------------------------------------------------
    # Dashboard interaction — THE FRAGILE LAYER (isolated + swappable)
    #
    # Everything below talks to the live Mediavine dashboard. The selectors,
    # the report URL, the date-range controls, and the export/XHR endpoint are
    # the parts that break when Mediavine changes its UI. They are deliberately
    # confined to `_login()` and `_scrape_period()` so the rest of the module
    # (input handling, checkpointing, yielding, callback) is stable. To swap
    # the scrape strategy (CSV export vs XHR JSON), edit `_scrape_period` only.
    # -----------------------------------------------------------------

    async def _login(self, page: Any, email: str, password: str) -> None:
        """Log into the Mediavine reporting dashboard.

        FRAGILE: selectors are unverified (no creds in this env). Confirm
        against the live login page before trusting a run.
        """
        await self.log(f"Navigating to Mediavine login: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # TODO(confirm): exact selectors for the April-2026 login form. These
        # are the conventional shapes; verify the real name/id/type attributes
        # in DevTools before a production run.
        try:
            await page.fill('input[type="email"], input[name="email"]', email)
            await page.fill('input[type="password"], input[name="password"]', password)
            await page.click('button[type="submit"], button:has-text("Log in")')
            # TODO(confirm): the post-login signal. Waiting for navigation away
            # from the login origin is a safe default; a dashboard-specific
            # selector (e.g. a nav avatar) would be more robust.
            await page.wait_for_url(f"{REPORTS_BASE_URL}/**", timeout=NAV_TIMEOUT_MS)
        except Exception as exc:
            raise RuntimeError(
                "Mediavine login flow failed — selectors likely changed. "
                "Recapture the login form against the live dashboard and update "
                f"_login(). Underlying error: {exc!r}"
            ) from exc

        await self.log("Mediavine login complete")

    async def _scrape_period(
        self, page: Any, period_start: str, period_end: str
    ) -> list[dict[str, Any]]:
        """Pull per-URL revenue rows for one date range.

        FRAGILE: this is the single swappable strategy method. It currently
        outlines the CSV-export path (preferred — the export is generally more
        stable than scraping the SPA's internal XHR JSON). The exact report
        URL, date-range controls, and export trigger/endpoint are unverified
        (`# TODO(confirm)`) and MUST be captured against the live dashboard.

        Returns a list of row dicts shaped for the extrachill-analytics revenue
        import: {slug, views, revenue, rpm} (period is added by the caller).

        Strategy choice: prefer triggering the dashboard's CSV export and
        parsing the downloaded file (`_parse_revenue_csv`). Fall back to reading
        the JSON the dashboard's own XHR returns only if the export proves less
        stable. Whichever is wired up, keep it confined to THIS method.
        """
        # TODO(confirm): the pages-report URL and how the date range is passed.
        # Many dashboards accept the range as query params; others require
        # interacting with a date-picker widget. Capture the real flow first.
        report_url = (
            f"{REPORTS_BASE_URL}/reports/pages"
            f"?start={period_start}&end={period_end}"
        )  # TODO(confirm) exact path + param names

        await self.log(f"Navigating to pages report: {report_url}")
        await page.goto(report_url, wait_until="networkidle")

        # ---- Preferred path: CSV export ----
        # TODO(confirm): the export trigger (a button) and whether it produces
        # a file download (Playwright `expect_download`) or an XHR that returns
        # CSV/JSON inline. The block below is the download shape; adapt to the
        # real control. Until confirmed, this raises so a run cannot silently
        # produce empty/fabricated data.
        try:
            async with page.expect_download(timeout=NAV_TIMEOUT_MS) as dl_info:
                # TODO(confirm): exact export button selector.
                await page.click(
                    'button:has-text("Export"), button:has-text("Download CSV")'
                )
            download = await dl_info.value
            path = await download.path()
            if path is None:
                raise RuntimeError("export download produced no file")
            with open(path, "r", encoding="utf-8") as fh:
                csv_text = fh.read()
            return self._parse_revenue_csv(csv_text)
        except Exception as exc:
            # Do NOT fabricate rows. Surface a clear, actionable failure so the
            # fragile layer gets fixed rather than masked.
            raise RuntimeError(
                "Mediavine pages-report export failed — the dashboard interaction "
                "(report URL, date-range control, or export trigger) is unverified "
                "and must be confirmed against the live April-2026 dashboard via a "
                "manual DevTools Network-tab capture. See the FRAGILITY NOTICE at "
                f"the top of this module. Underlying error: {exc!r}"
            ) from exc

    @staticmethod
    def _parse_revenue_csv(csv_text: str) -> list[dict[str, Any]]:
        """Parse a Mediavine pages-report CSV into normalized revenue rows.

        Maps the export's columns onto the shape the extrachill-analytics
        revenue import expects: {slug, views, revenue, rpm}. Unknown/extra
        columns are ignored; missing numeric values default to 0.

        TODO(confirm): the EXACT export column headers. The header aliases
        below are best-effort guesses — confirm against a real export and
        prune/extend. Parsing logic is intentionally tolerant so a header
        rename does not silently drop a column without being noticed in review.
        """
        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(csv_text))

        # Candidate header aliases (lowercased). TODO(confirm) against a real export.
        url_keys = ("url", "page", "page url", "slug", "path")
        views_keys = ("views", "pageviews", "page views", "sessions", "impressions")
        revenue_keys = ("revenue", "earnings", "total revenue", "est. revenue")
        rpm_keys = ("rpm", "page rpm", "session rpm")

        def _pick(record: dict[str, str], keys: tuple[str, ...]) -> Optional[str]:
            lowered = {(k or "").strip().lower(): v for k, v in record.items()}
            for key in keys:
                if key in lowered and lowered[key] not in (None, ""):
                    return lowered[key]
            return None

        def _num(value: Optional[str]) -> float:
            if value is None:
                return 0.0
            cleaned = value.replace("$", "").replace(",", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return 0.0

        for record in reader:
            slug = _pick(record, url_keys)
            if not slug:
                continue
            rows.append(
                {
                    "slug": slug.strip(),
                    "views": int(_num(_pick(record, views_keys))),
                    "revenue": _num(_pick(record, revenue_keys)),
                    "rpm": _num(_pick(record, rpm_keys)),
                }
            )

        return rows

"""
app/utils/github_issue_reporter.py
────────────────────────────────────
Auto-creates GitHub Issues when unhandled backend errors occur.

Features:
  • Deduplication  — won't open the same issue twice (checks by title hash)
  • Rate limiting  — max 10 issues per hour to avoid runaway spam
  • Async-safe     — uses httpx.AsyncClient (already in requirements.txt)
  • Environment-aware — disabled in development by default

Environment variables (add to your .env / Docker env):
    GITHUB_TOKEN          Personal Access Token with repo scope
    GITHUB_REPO           owner/repo  (default: YouthStack-Dev/fleet_manager)
    GITHUB_AUTO_ISSUES    "1" to enable  (default: "0" — disabled in dev)
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Optional

import httpx

from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config (read once at import time)
# ─────────────────────────────────────────────────────────────────────────────
_TOKEN    = os.getenv("GITHUB_TOKEN", "")
_REPO     = os.getenv("GITHUB_REPO",  "YouthStack-Dev/fleet_manager")
_ENABLED  = os.getenv("GITHUB_AUTO_ISSUES", "0") == "1"
_API_BASE = "https://api.github.com"

# ─────────────────────────────────────────────────────────────────────────────
# Simple in-process rate limiter + dedup cache
# ─────────────────────────────────────────────────────────────────────────────
_RATE_WINDOW   = 3600          # seconds (1 hour)
_RATE_MAX      = 10            # max issues per window
_rate_log: list[float] = []   # timestamps of recent reports
_seen_hashes: set[str] = set() # title hashes already reported this process run


def _is_rate_limited() -> bool:
    """Return True if we've hit the hourly cap."""
    now = time.monotonic()
    # Evict entries older than the window
    _rate_log[:] = [t for t in _rate_log if now - t < _RATE_WINDOW]
    if len(_rate_log) >= _RATE_MAX:
        return True
    _rate_log.append(now)
    return False


def _title_hash(title: str) -> str:
    return hashlib.sha1(title.lower().strip().encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
async def report_error_to_github(
    *,
    title: str,
    traceback_str: str,
    error_type: str  = "UnhandledException",
    path: str        = "",
    method: str      = "",
    extra: Optional[dict] = None,
) -> bool:
    """
    Create a GitHub Issue for an unhandled backend exception.
    Returns True if an issue was opened, False otherwise.

    Call this as a fire-and-forget asyncio task from middleware:

        asyncio.create_task(
            report_error_to_github(
                title=f"[Auto] {type(e).__name__}: {str(e)[:120]}",
                traceback_str=traceback.format_exc(),
                error_type=type(e).__name__,
                path=request.url.path,
                method=request.method,
            )
        )
    """
    if not _ENABLED:
        logger.debug("GitHub auto-issue reporting is disabled (GITHUB_AUTO_ISSUES != 1)")
        return False

    if not _TOKEN:
        logger.warning("GITHUB_TOKEN not set — cannot report error to GitHub")
        return False

    # Deduplicate by title hash
    h = _title_hash(title)
    if h in _seen_hashes:
        logger.debug(f"GitHub issue already reported this session: {title[:80]}")
        return False
    _seen_hashes.add(h)

    # Rate limit
    if _is_rate_limited():
        logger.warning(f"GitHub issue rate limit reached ({_RATE_MAX}/hr) — suppressing: {title[:80]}")
        return False

    body = _build_body(
        title=title,
        traceback_str=traceback_str,
        error_type=error_type,
        path=path,
        method=method,
        extra=extra or {},
    )

    labels = ["bug", "backend", "auto-reported"]

    # Critical heuristics
    critical_keywords = ["database", "connection", "timeout", "sqlalchemy", "psycopg"]
    if any(kw in traceback_str.lower() for kw in critical_keywords):
        labels.append("critical")
    else:
        labels.append("high-priority")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_API_BASE}/repos/{_REPO}/issues",
                json={"title": title[:255], "body": body, "labels": labels},
                headers={
                    "Authorization": f"Bearer {_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )

        if resp.status_code == 201:
            issue = resp.json()
            logger.info(f"🐛 GitHub issue created: #{issue['number']} — {issue['html_url']}")
            return True
        else:
            logger.error(f"Failed to create GitHub issue: HTTP {resp.status_code} — {resp.text[:300]}")
            # Remove from seen so it can be retried
            _seen_hashes.discard(h)
            return False

    except Exception as exc:
        logger.error(f"GitHub issue reporter exception: {exc}")
        _seen_hashes.discard(h)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Helper — build issue body markdown
# ─────────────────────────────────────────────────────────────────────────────
def _build_body(
    title: str,
    traceback_str: str,
    error_type: str,
    path: str,
    method: str,
    extra: dict,
) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")

    lines = [
        "## 🤖 Auto-Reported Backend Error",
        "",
        "> This issue was automatically created by the Fleet Manager error handler.",
        "",
        "---",
        "",
        "### 📋 Summary",
        "",
        f"| Field        | Value |",
        f"|--------------|-------|",
        f"| **Error**    | `{error_type}` |",
        f"| **Endpoint** | `{method} {path}` |",
        f"| **Time**     | {now} |",
    ]

    if extra:
        for k, v in extra.items():
            lines.append(f"| **{k}** | {v} |")

    lines += [
        "",
        "---",
        "",
        "### 🔍 Stack Trace",
        "",
        "```python",
        traceback_str[:6000],  # GitHub issue body limit is ~65k, keep it sane
        "```",
        "",
        "---",
        "",
        "### ✅ Action Required",
        "",
        "- [ ] Reproduce on staging",
        "- [ ] Identify root cause",
        "- [ ] Fix and deploy",
        "- [ ] Add `testing` label when deployed",
        "- [ ] Tester verifies and closes",
    ]

    return "\n".join(lines)

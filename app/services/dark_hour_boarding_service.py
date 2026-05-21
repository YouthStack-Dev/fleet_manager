"""
app/services/dark_hour_boarding_service.py
------------------------------------------
Feature 12 — Female Employee Dark-Hour Boarding Block

Pure-function check_dark_hour_boarding() — no database queries.

Algorithm
---------
1. If dark_hour_boarding_mode is 'off'  → always allow (ok=True, no warnings).
2. If employee gender is not FEMALE     → always allow.
3. If escort_required_for_women is False → always allow.
4. If either dark-window time is None   → always allow (feature not configured).
5. Determine whether now_time falls inside the configured dark window:
       Overnight window (start > end):  now >= start  OR  now <= end
       Same-day window  (start <= end): start <= now <= end
6. If NOT inside the dark window        → allow.
7. Inside the dark window:
   - If escort_present_and_boarded is True → allow (employee is safe).
   - Else (no boarded escort):
         'warn'  → ok=True,  warnings=["dark_hour_no_escort"]
         'block' → ok=False, error_code="DARK_HOUR_NO_ESCORT"

Return value
------------
dict with keys:
    ok          : bool
    warnings    : list[str]   – non-empty only in warn-mode trigger
    error_code  : str | None  – set only on hard-block

No exceptions are raised; the function is intentionally side-effect-free.
"""

from __future__ import annotations

from datetime import time
from typing import Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_dark_hour_boarding(
    gender: Optional[str],
    escort_present_and_boarded: bool,
    cfg,                    # TenantConfig ORM object (or any object with the required attrs)
    now_time: time,
) -> dict:
    """
    Evaluate whether a female employee's boarding should be warned/blocked.

    Parameters
    ----------
    gender                    : Employee gender string (e.g. "Female", "Male").
                                Pass None to treat as unknown (allow through).
    escort_present_and_boarded: True when route.assigned_escort_id is set
                                AND route.escort_boarded is True.
                                (The ESCORT_NOT_BOARDED guard in start_trip already
                                blocks the scenario where escort is assigned but has
                                not yet boarded, so at this point the value is either
                                True or the route has no escort at all.)
    cfg                       : TenantConfig instance with attributes:
                                    dark_hour_boarding_mode ('off'|'warn'|'block')
                                    escort_required_for_women (bool)
                                    escort_required_start_time (time | None)
                                    escort_required_end_time   (time | None)
    now_time                  : Current wall-clock time (IST or whichever TZ the
                                tenant times are configured in).

    Returns
    -------
    dict:
        ok         (bool)
        warnings   (list[str])  – ["dark_hour_no_escort"] when in warn mode
        error_code (str | None) – "DARK_HOUR_NO_ESCORT" when in block mode
    """
    _allow = {"ok": True, "warnings": [], "error_code": None}

    # ── Gate 1: feature enabled? ────────────────────────────────────────────
    mode = getattr(cfg, "dark_hour_boarding_mode", "off") or "off"
    if mode == "off":
        return _allow

    # ── Gate 2: only applies to female employees ─────────────────────────────
    if not gender or gender.lower() != "female":
        return _allow

    # ── Gate 3: tenant has escort requirement for women ──────────────────────
    if not getattr(cfg, "escort_required_for_women", False):
        return _allow

    # ── Gate 4: dark window must be fully configured ─────────────────────────
    dark_start: Optional[time] = getattr(cfg, "escort_required_start_time", None)
    dark_end:   Optional[time] = getattr(cfg, "escort_required_end_time",   None)
    if dark_start is None or dark_end is None:
        return _allow

    # ── Gate 5: is now_time inside the dark window? ──────────────────────────
    if not _in_dark_window(now_time, dark_start, dark_end):
        return _allow

    # ── Gate 6: escort is present and boarded → safe ─────────────────────────
    if escort_present_and_boarded:
        return _allow

    # ── Dark-hour + no-escort: apply mode ────────────────────────────────────
    if mode == "warn":
        return {"ok": True, "warnings": ["dark_hour_no_escort"], "error_code": None}

    # mode == "block"
    return {"ok": False, "warnings": [], "error_code": "DARK_HOUR_NO_ESCORT"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _in_dark_window(now: time, start: time, end: time) -> bool:
    """
    Return True when *now* falls inside [start, end].

    Overnight window (start > end, e.g. 22:00 → 06:00):
        now >= 22:00  OR  now <= 06:00

    Same-day window (start <= end, e.g. 20:00 → 23:00):
        now >= 20:00  AND  now <= 23:00
    """
    if start > end:
        # Overnight span — wraps past midnight
        return now >= start or now <= end
    # Intra-day span
    return start <= now <= end

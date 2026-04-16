#!/usr/bin/env python3
"""
setup_github_labels.py
─────────────────────
Creates all required labels for ETS Fleet Manager issue tracking.
Run this once on any new repository.

Usage:
    python scripts/setup_github_labels.py
    python scripts/setup_github_labels.py --token ghp_xxx --repo YouthStack-Dev/fleet_manager
    GITHUB_TOKEN=ghp_xxx python scripts/setup_github_labels.py
"""
import os
import sys
import argparse
import requests

# ─────────────────────────────────────────────────────────────────────────────
# Label definitions
# ─────────────────────────────────────────────────────────────────────────────
LABELS = [
    # ── Type ──────────────────────────────────────────────────────────────────
    {"name": "bug",             "color": "d73a4a", "description": "Something isn't working"},
    {"name": "feature",         "color": "0075ca", "description": "New feature or request"},

    # ── Source ────────────────────────────────────────────────────────────────
    {"name": "frontend",        "color": "e4e669", "description": "Frontend (UI/app) issue"},
    {"name": "backend",         "color": "1d76db", "description": "Backend (API/DB) issue"},

    # ── Priority ──────────────────────────────────────────────────────────────
    {"name": "critical",        "color": "b60205", "description": "System down / data loss — same day fix"},
    {"name": "high-priority",   "color": "e11d48", "description": "Feature broken for users — within 24 hrs"},
    {"name": "medium-priority", "color": "f97316", "description": "Partial impact — 2-3 days"},
    {"name": "low-priority",    "color": "6b7280", "description": "Minor / cosmetic — backlog"},

    # ── Workflow / Status ──────────────────────────────────────────────────────
    {"name": "status: open",     "color": "c2e0c6", "description": "New — not yet assigned"},
    {"name": "status: assigned", "color": "bfd4f2", "description": "Assigned to a developer"},
    {"name": "in-progress",      "color": "0e8a16", "description": "Actively being worked on"},
    {"name": "testing",          "color": "fbca04", "description": "On staging — awaiting tester verification"},
    {"name": "status: done",     "color": "cccccc", "description": "Verified and closed by tester"},

    # ── Special ───────────────────────────────────────────────────────────────
    {"name": "auto-reported",   "color": "8b5cf6", "description": "Auto-created by backend error handler"},
    {"name": "needs-info",      "color": "e4e669", "description": "More information needed before work can start"},
    {"name": "wont-fix",        "color": "ffffff", "description": "Out of scope — will not be addressed"},
    {"name": "duplicate",       "color": "cfd3d7", "description": "Already tracked in another issue"},
]

GITHUB_API = "https://api.github.com"


def get_existing_labels(session: requests.Session, repo: str) -> dict[str, dict]:
    """Return {name: label_data} for all labels already on the repo."""
    labels = {}
    page = 1
    while True:
        resp = session.get(f"{GITHUB_API}/repos/{repo}/labels", params={"per_page": 100, "page": page})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        for label in data:
            labels[label["name"]] = label
        page += 1
    return labels


def create_or_update_label(session: requests.Session, repo: str, label: dict, existing: dict) -> str:
    """Create label if missing, update it if color/description differs. Returns 'created'/'updated'/'skipped'."""
    name = label["name"]

    if name in existing:
        ex = existing[name]
        if ex["color"] == label["color"] and ex.get("description") == label.get("description", ""):
            return "skipped"
        # Update
        resp = session.patch(
            f"{GITHUB_API}/repos/{repo}/labels/{requests.utils.quote(name, safe='')}",
            json={"color": label["color"], "description": label.get("description", "")},
        )
        resp.raise_for_status()
        return "updated"
    else:
        # Create
        resp = session.post(
            f"{GITHUB_API}/repos/{repo}/labels",
            json=label,
        )
        resp.raise_for_status()
        return "created"


def main():
    parser = argparse.ArgumentParser(description="Set up GitHub labels for ETS Fleet Manager")
    parser.add_argument("--token", help="GitHub Personal Access Token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--repo",  default="YouthStack-Dev/fleet_manager", help="owner/repo")
    args = parser.parse_args()

    token = args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌  GitHub token required. Pass --token or set GITHUB_TOKEN env var.", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    repo = args.repo
    print(f"\n🏷  Setting up labels for: {repo}\n")

    existing = get_existing_labels(session, repo)

    created = updated = skipped = 0
    for label in LABELS:
        result = create_or_update_label(session, repo, label, existing)
        icon   = {"created": "✅", "updated": "🔄", "skipped": "⏭ "}[result]
        print(f"  {icon}  {result:8s}  →  {label['name']}")
        if result == "created": created += 1
        elif result == "updated": updated += 1
        else: skipped += 1

    print(f"\n📊  Done — {created} created · {updated} updated · {skipped} skipped\n")


if __name__ == "__main__":
    main()

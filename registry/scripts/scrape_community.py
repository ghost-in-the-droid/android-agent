#!/usr/bin/env python3
"""Scrape community skills from GitHub repos tagged 'android-agent-skill'.

Usage:
    GITHUB_TOKEN=ghp_... python scripts/scrape_community.py

Searches GitHub for repos with the 'android-agent-skill' topic,
fetches their skill.yaml, validates required fields, and writes
community.json to the repo root.

Requires:
    - GITHUB_TOKEN environment variable (for API rate limits)
    - pip install pyyaml requests
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = REPO_ROOT / "community.json"
GITHUB_API = "https://api.github.com"
REQUIRED_FIELDS = ["name", "description", "version", "app_package"]


def get_headers() -> dict:
    """Get GitHub API headers with authentication."""
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "android-agent-skill-scraper",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    else:
        print("WARNING: GITHUB_TOKEN not set — API rate limits will be very low (60/hour)")
    return headers


def search_repos(headers: dict) -> list[dict]:
    """Search GitHub for repos tagged 'android-agent-skill'."""
    repos = []
    page = 1
    per_page = 30

    while True:
        url = f"{GITHUB_API}/search/repositories"
        params = {
            "q": "topic:android-agent-skill",
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page,
        }

        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 403:
            # Rate limited
            reset_time = int(resp.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - int(time.time()), 10)
            print(f"  Rate limited. Waiting {wait}s ...")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            print(f"  ERROR: GitHub API returned {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        items = data.get("items", [])
        repos.extend(items)

        total = data.get("total_count", 0)
        print(f"  Page {page}: {len(items)} repos (total: {total})")

        if len(items) < per_page or len(repos) >= total:
            break

        page += 1
        time.sleep(1)  # Be polite to the API

    return repos


def fetch_skill_yaml(repo: dict, headers: dict) -> dict | None:
    """Fetch and parse skill.yaml from a repo's default branch."""
    full_name = repo["full_name"]
    default_branch = repo.get("default_branch", "main")

    # Try raw URL for skill.yaml
    raw_url = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/skill.yaml"

    try:
        resp = requests.get(raw_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        return yaml.safe_load(resp.text)
    except Exception as e:
        print(f"  ERROR fetching skill.yaml from {full_name}: {e}")
        return None


def validate_skill(data: dict) -> bool:
    """Check that skill.yaml has all required fields."""
    if not isinstance(data, dict):
        return False
    for field in REQUIRED_FIELDS:
        if field not in data:
            return False
    return True


def build_entry(repo: dict, skill_data: dict) -> dict:
    """Build a community index entry from repo + skill data."""
    exports = skill_data.get("exports", {})

    actions_raw = exports.get("actions", [])
    actions = []
    for a in actions_raw:
        if isinstance(a, dict):
            actions.append(a.get("name", str(a)))
        else:
            actions.append(str(a))

    workflows_raw = exports.get("workflows", [])
    workflows = []
    for w in workflows_raw:
        if isinstance(w, dict):
            workflows.append(w.get("name", str(w)))
        else:
            workflows.append(str(w))

    return {
        "name": skill_data.get("name", repo["name"]),
        "display_name": skill_data.get("display_name",
                                       skill_data.get("name", repo["name"]).replace("_", " ").replace("-", " ").title()),
        "description": skill_data.get("description", repo.get("description", "")),
        "version": skill_data.get("version", "0.0.0"),
        "app_package": skill_data.get("app_package"),
        "author": skill_data.get("author", repo.get("owner", {}).get("login", "unknown")),
        "license": skill_data.get("license", "unknown"),
        "actions": actions,
        "workflows": workflows,
        "elements_count": 0,  # Can't easily count from remote
        "tested_on": skill_data.get("tested_on", []),
        "source": "community",
        "repo_url": repo["html_url"],
        "stars": repo.get("stargazers_count", 0),
        "last_updated": repo.get("updated_at", ""),
    }


def main():
    headers = get_headers()

    print("Searching GitHub for android-agent-skill repos ...")
    repos = search_repos(headers)
    print(f"Found {len(repos)} repos")

    entries = []
    for repo in repos:
        full_name = repo["full_name"]
        print(f"  Checking {full_name} ...")

        skill_data = fetch_skill_yaml(repo, headers)
        if skill_data is None:
            print(f"    SKIP: no skill.yaml found")
            continue

        if not validate_skill(skill_data):
            print(f"    SKIP: skill.yaml missing required fields")
            continue

        entry = build_entry(repo, skill_data)
        entries.append(entry)
        print(f"    OK: {entry['name']} ({len(entry['actions'])} actions, {entry['stars']} stars)")

    # Sort by stars (descending), then name
    entries.sort(key=lambda e: (-e.get("stars", 0), e["name"]))

    community = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill_count": len(entries),
        "skills": entries,
    }

    OUTPUT_FILE.write_text(json.dumps(community, indent=2) + "\n")
    print(f"\nWrote {OUTPUT_FILE} — {len(entries)} community skills")


if __name__ == "__main__":
    main()

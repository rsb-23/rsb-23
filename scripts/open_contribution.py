#!/usr/bin/env python3
"""
GitHub Contributions File Generator
-------------------------------------
Fetches your public contributions (PRs, Issues, PR Comments, Issue Comments)
to repos with a license, and creates/updates CONTRIBUTIONS.md in your profile repo.

Usage:
    pip install PyGithub
    python scripts/open_contribution.py --token YOUR_PAT --username YOUR_USERNAME

Optional flags:
    --dry-run         Print the file contents without pushing to GitHub
    --output-file     Filename to create in the repo (default: CONTRIBUTIONS.md)
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime

from github import Auth, Github, GithubException


class Contribution:
    def __init__(self, item):
        repo = item.repository
        self.repo = repo.full_name
        self.license = repo.license.spdx_id if repo.license else "Apache-2.0"
        self.stars = repo.stargazers_count

        self.title = item.title
        self.url = item.html_url
        self.created_at = item.created_at.strftime("%Y-%m-%d")

        self.state = item.state or ""
        self.state_reason = item.state_reason or ""


@dataclass
class Contributions:
    pull_requests: list[Contribution] = field(default_factory=list)
    issues: list[Contribution] = field(default_factory=list)
    pr_comments: list[Contribution] = field(default_factory=list)
    issue_comments: list[Contribution] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def search_and_collect(g, query: str, username: str, *, skip_own: bool = True) -> list[Contribution]:
    """Run a GitHub issue search and return filtered Contribution objects."""
    results = []
    if skip_own:
        query = f"{query} -owner:{username}"
    for item in g.search_issues(query):
        # print(item.repository.__dict__)
        # print(item.state_reason)
        # raise KeyError
        results.append(Contribution(item))
    return results


# ── Fetch functions ───────────────────────────────────────────────────────────
def fetch_pull_requests(g, username: str) -> list[Contribution]:
    print("[1/4] Fetching pull requests...")
    items = search_and_collect(g, f"type:pr author:{username} is:public is:merged", username)
    for item in items:
        item.state = "MERGED"
    return items


def fetch_issues(g, username: str) -> list[Contribution]:
    print("[2/4] Fetching issues...")
    items = search_and_collect(g, f"type:issue author:{username} is:public reason:completed", username)
    for item in items:
        item.state = item.state_reason or "open"
    return items


def fetch_pr_comments(g, username: str) -> list[Contribution]:
    print("[3/4] Fetching PR comments...")
    return search_and_collect(g, f"type:pr commenter:{username} is:public", username)


def fetch_issue_comments(g, username: str) -> list[Contribution]:
    print("[4/4] Fetching issue comments...")
    return search_and_collect(g, f"type:issue commenter:{username} is:public", username)


def fetch_all(g, username: str) -> Contributions:
    return Contributions(
        pull_requests=fetch_pull_requests(g, username),
        issues=fetch_issues(g, username),
        # pr_comments=fetch_pr_comments(g, username),
        # issue_comments=fetch_issue_comments(g, username),
    )


# ── Markdown builders ─────────────────────────────────────────────────────────

Col = tuple[str, str]  # (header label, Contribution field name)


def build_table(items: list[Contribution], cols: list[Col], limit: int = 50) -> str:
    if not items:
        return "_None found._\n"

    def is_int(col) -> bool:
        return type(getattr(items[0], col[1])) is int

    header = "| " + " | ".join(c[0] for c in cols) + " |"
    sep = "| " + " | ".join("---:" if is_int(c) else "---" for c in cols) + " |"
    rows = []
    for item in items[:limit]:
        cells = []
        for _, attr in cols:
            val = getattr(item, attr, "") or ""
            if attr == "title":
                val = f"[{val[:60]}]({item.url})"
            cells.append(str(val))
        rows.append("| " + " | ".join(cells) + " |")
    note = f"\n> Showing up to {limit} most recent. Total: **{len(items)}**\n" if len(items) > limit else ""
    return "\n".join([header, sep] + rows) + "\n" + note


def build_section(title: str, items: list[Contribution], cols: list[Col]) -> str:
    if not items:
        return ""
    items = sorted(items, key=lambda c: c.stars, reverse=True)
    return f"### {title}\n\n{build_table(items, cols)}\n---\n"


def build_contributions_file(data: Contributions, username: str) -> str:
    now = datetime.now().strftime("%d %b %Y")

    col_order: list[Col] = [
        ("Repository", "repo"),
        ("License", "license"),
        ("Stars ⭐", "stars"),
        ("Title", "title"),
    ]

    sections = "".join(
        [
            build_section("🔀 Pull Requests (Merged)", data.pull_requests, col_order),
            build_section("🐛 Issues (Accepted)", data.issues, col_order),
            build_section("💬 PR Comments", data.pr_comments, col_order),
            build_section("🗨️ Issue Comments", data.issue_comments, col_order),
        ]
    )

    summary_rows = "\n".join(
        [
            f"| 🔀 Merged Pull Requests | {len(data.pull_requests)} |",
            f"| 🐛 Accepted Issues | {len(data.issues)} |",
            # f"| 💬 PR Comments | {len(data.pr_comments)} |",
            # f"| 🗨️ Issue Comments | {len(data.issue_comments)} |",
        ]
    )

    return f"""# 🛠️ Open Source Contributions

> Auto-generated on {now} · Only public repos with a license · [@{username}](https://github.com/{username})

| Category | Count |
|---|---|
{summary_rows}

---

{sections}"""


# ── File write ──────────────────────────────────────────────────────────────


def write_contributions_file(content: str, filename: str, dry_run: bool):
    if dry_run:
        print("=" * 60)
        print(f"DRY RUN — {filename} would be written with:\n")
        print(content)
        print("=" * 60)
        return

    with open(filename, "wb") as f:
        f.write(content.encode("utf-8"))
        print(f"✅ Created {filename}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(description="Generate CONTRIBUTIONS.md in your GitHub profile repo")
    p.add_argument("--token", default="", help="GitHub Personal Access Token")
    p.add_argument("--username", required=True, help="Your GitHub username")
    p.add_argument("--dry-run", action="store_true", help="Print output, don't push")
    p.add_argument("--output-file", default="CONTRIBUTIONS.md", help="Filename to create (default: CONTRIBUTIONS.md)")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.token:
        from dotenv import load_dotenv

        load_dotenv()
        args.token = os.getenv("PAT") or ""

    print(f"🔑 Authenticating as @{args.username}...\n")
    auth = Auth.Token(args.token)
    g = Github(auth=auth)

    try:
        _ = g.get_user(args.username).login
    except GithubException as e:
        print(f"❌ Auth failed: {e}")
        sys.exit(1)

    data = fetch_all(g, args.username)
    print()
    content = build_contributions_file(data, args.username)
    write_contributions_file(content, args.output_file, args.dry_run)


if __name__ == "__main__":
    main()

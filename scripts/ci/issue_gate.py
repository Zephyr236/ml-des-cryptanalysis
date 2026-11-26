#!/usr/bin/env python3
"""issue-gate: a pull request may only merge when its issues are resolved.

Checks
------
1. The PR body uses the required template sections.
2. The PR closes at least one issue (``Closes #N``), unless the body
   carries ``No-Issue: <reason>``.
3. Every issue referenced with ``Refs #N`` is already closed; a merge
   must not leave a referenced issue open.
4. No open issue labelled ``blocker`` exists in the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

CLOSING_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)"
)
REF_RE = re.compile(r"(?i)\brefs?\s+#(\d+)")
NO_ISSUE_RE = re.compile(r"No-Issue:\s*(\S.{9,})")
REQUIRED_SECTIONS = ("## Summary", "## Linked issues", "## Results", "## Risk")


def api(url: str, token: str) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "des-ml-ci",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def error(message: str) -> None:
    print(f"::error::{message}")
    print(f"ERROR: {message}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    if not args.event_path or not Path(args.event_path).exists():
        error("GITHUB_EVENT_PATH is missing; this gate only runs on pull_request events")
        return 1
    if not args.repo or not args.token:
        error("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
        return 1

    event = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
    pull = event.get("pull_request")
    if pull is None:
        error("not a pull_request event")
        return 1

    body = pull.get("body") or ""
    number = pull["number"]
    problems: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section.lower() not in body.lower():
            problems.append(f"PR body is missing the '{section}' section")

    closing = {int(value) for value in CLOSING_RE.findall(body)}
    references = {int(value) for value in REF_RE.findall(body)} - closing
    waiver = NO_ISSUE_RE.search(body)

    if not closing and not waiver:
        problems.append(
            "PR does not close an issue. Add 'Closes #N' or 'No-Issue: <reason>' to the body."
        )
    if waiver and len(waiver.group(1).strip()) < 10:
        problems.append("No-Issue waiver needs a substantive reason")

    for issue_number in sorted(references):
        try:
            issue = api(f"https://api.github.com/repos/{args.repo}/issues/{issue_number}", args.token)
        except urllib.error.HTTPError as exc:
            problems.append(f"cannot read referenced issue #{issue_number}: HTTP {exc.code}")
            continue
        if issue.get("state") != "closed":
            problems.append(
                f"referenced issue #{issue_number} is still open; resolve it or use a closing keyword"
            )

    try:
        open_blockers = api(
            f"https://api.github.com/repos/{args.repo}/issues?state=open&labels=blocker&per_page=100",
            args.token,
        )
    except urllib.error.HTTPError as exc:
        problems.append(f"cannot list blocker issues: HTTP {exc.code}")
        open_blockers = []

    for issue in open_blockers:
        if "pull_request" in issue:
            continue
        problems.append(f"blocker issue #{issue['number']} is still open: {issue['title']}")

    if not closing and not waiver:
        problems.append(f"PR #{number} resolves no issue")

    if problems:
        for problem in problems:
            error(problem)
        return 1

    if closing:
        print(f"issue-gate: closes {sorted(closing)}")
    else:
        print(f"issue-gate: waived ({waiver.group(1).strip()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

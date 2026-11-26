#!/usr/bin/env python3
"""main-provenance: every commit that lands on ``main`` must be a merge.

GitHub requires a repository to keep at least one of squash/rebase
enabled, so the merge-method policy cannot be enforced by settings
alone.  This audit runs on every push to ``main``, walks the
first-parent chain of the push, and fails if a commit has fewer than two
parents.  It also files an issue so the violation is visible even though
the commit already landed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ZERO = re.compile(r"^0+$")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def parents(commit: str) -> list[str]:
    return git("rev-list", "--parents", "-n", "1", commit).split()


def api(url: str, token: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "des-ml-provenance",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def find_open_issue(repo: str, token: str, title: str) -> bool:
    query = urllib.parse.quote(f'repo:{repo} is:issue is:open in:title "{title}"')
    try:
        result = api(f"https://api.github.com/search/issues?q={query}", token)
    except urllib.error.HTTPError:
        return False
    return bool(result.get("items"))


def file_issue(repo: str, token: str, commits: list[str]) -> None:
    title = "[provenance] non-merge commit landed on main"
    if find_open_issue(repo, token, title):
        return
    detail = "\n".join(f"- `{commit}`" for commit in commits)
    api(
        f"https://api.github.com/repos/{repo}/issues",
        token,
        method="POST",
        payload={
            "title": title,
            "body": (
                "The `main-provenance` audit found commits on `main` that are not "
                "merge commits:\n\n"
                f"{detail}\n\n"
                "A squash or rebase merge rewrote the PR history, so any result "
                "manifest whose `code_sha` pointed into that PR is no longer an "
                "ancestor of `main`. Re-merge the affected PR with a merge commit, "
                "or record an archive tag for its head (see ADR-0001).\n\n"
                "This issue is filed automatically and is advisory; the workflow "
                "run itself is red."
            ),
            "labels": ["reproducibility"],
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()

    if ZERO.match(args.before):
        print("initial push; no ancestry to check")
        return 0

    commits = git(
        "rev-list", "--first-parent", "--reverse", f"{args.before}..{args.after}"
    ).splitlines()
    if not commits:
        print("no first-parent commits in this push")
        return 0

    offenders = [commit for commit in commits if len(parents(commit)) < 3]
    if not offenders:
        print(f"all {len(commits)} pushed commit(s) are merge commits")
        return 0

    for commit in offenders:
        subject = git("log", "-1", "--format=%s", commit)
        print(f"::error::non-merge commit on main: {commit} {subject}")
    if args.repo and args.token:
        try:
            file_issue(args.repo, args.token, offenders)
        except Exception as exc:  # noqa: BLE001 - issue filing is best effort
            print(f"could not file issue: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

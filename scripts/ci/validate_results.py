#!/usr/bin/env python3
"""results-gate: every pull request must carry a reproducible run manifest.

Rules
-----
1. The PR must change at least one ``results/**/manifest.json``.
2. Every changed manifest must validate against the schema in
   :mod:`des_ml.manifest` and its ``config.yaml`` hash must match.
3. The manifest's ``code_sha`` must be a commit inside this PR.
4. ``results/LATEST.json`` must be updated and point at one of the runs.
5. No secrets may appear in result files.
6. Documentation-only work may waive the gate with
   ``Results-Exempt: <reason>`` in the PR body (reason required).

This script is deterministic and uses only the standard library plus
PyYAML.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from des_ml.manifest import validate_manifest  # noqa: E402

SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"user!\?_"),
    re.compile(r"(?i)\b(password|passwd|secret)\b\s*[:=]\s*['\"]?[^\s'\"#]{6,}"),
)
MAX_RESULT_BYTES = 5 * 1024 * 1024


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def changed_files(base: str, head: str) -> list[str]:
    output = git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}")
    return [line for line in output.splitlines() if line]


def error(message: str) -> None:
    print(f"::error::{message}")
    print(f"ERROR: {message}", file=sys.stderr)


def notice(message: str) -> None:
    print(f"::notice::{message}")


def check_secrets(path: Path) -> list[str]:
    problems: list[str] = []
    if not path.is_file() or path.stat().st_size > MAX_RESULT_BYTES:
        return problems
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return problems
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            problems.append(f"possible secret in {path.relative_to(REPO_ROOT)} ({pattern.pattern})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base ref, e.g. origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--body-file", default=None, help="File containing the PR body")
    args = parser.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ""
    try:
        files = changed_files(args.base, args.head)
        commits = set(git("rev-list", f"{args.base}..{args.head}").splitlines())
    except subprocess.CalledProcessError as exc:
        error(f"git failed while comparing {args.base}...{args.head}: {exc.stderr.strip()}")
        return 1

    manifest_paths = [
        Path(name)
        for name in files
        if name.startswith("results/") and name.endswith("manifest.json")
    ]

    if not manifest_paths:
        waiver = re.search(r"Results-Exempt:\s*(\S.{9,})", body)
        if waiver:
            notice(f"results gate waived: {waiver.group(1).strip()}")
            return 0
        error(
            "No results/manifest.json was added or updated. Run the experiment on the GPU "
            "host, commit the result directory, and update results/LATEST.json. "
            "If this PR cannot produce a result, add 'Results-Exempt: <reason>' to the body."
        )
        return 1

    problems: list[str] = []
    for relative in manifest_paths:
        manifest_path = REPO_ROOT / relative
        run_dir = manifest_path.parent
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{relative}: cannot read manifest: {exc}")
            continue

        config_path = run_dir / "config.yaml"
        config_bytes = config_path.read_bytes() if config_path.exists() else None
        problems.extend(f"{relative}: {problem}" for problem in validate_manifest(manifest, config_bytes=config_bytes))

        if manifest.get("status") != "completed":
            problems.append(f"{relative}: status is {manifest.get('status')!r}, expected 'completed'")
        code_sha = str(manifest.get("code_sha", ""))
        if not any(commit.startswith(code_sha) or code_sha.startswith(commit) for commit in commits):
            problems.append(
                f"{relative}: code_sha {code_sha[:12]} is not a commit in {args.base}..{args.head}. "
                "Re-run the experiment on the commit you are proposing."
            )
        metrics = manifest.get("metrics", {}).get("final", {})
        if not metrics:
            problems.append(f"{relative}: metrics.final is empty")
        if "metrics.json" not in manifest.get("artifacts", []):
            problems.append(f"{relative}: metrics.json missing from artifacts")

        for child in run_dir.rglob("*"):
            if child.is_file():
                if child.stat().st_size > MAX_RESULT_BYTES:
                    problems.append(f"{child.relative_to(REPO_ROOT)} exceeds 5 MiB; link large artefacts instead")
                problems.extend(check_secrets(child))

    latest_path = REPO_ROOT / "results/LATEST.json"
    if "results/LATEST.json" not in files:
        problems.append("results/LATEST.json was not updated")
    else:
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"results/LATEST.json is unreadable: {exc}")
        else:
            target = latest.get("path", "")
            if not target:
                problems.append("results/LATEST.json has no path")
            elif not (REPO_ROOT / "results" / target / "manifest.json").exists():
                problems.append(f"results/LATEST.json points at missing run: {target}")
            elif f"results/{target}/manifest.json" not in [str(p) for p in manifest_paths]:
                problems.append("results/LATEST.json must point at a manifest changed by this PR")

    if problems:
        for problem in problems:
            error(problem)
        return 1

    notice(f"validated {len(manifest_paths)} result manifest(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

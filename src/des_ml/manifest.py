"""Result manifests.

Every experiment that is allowed to influence a claim in this repository
must produce a manifest.  The manifest ties a set of metrics to an
exact code revision, a config hash, a seed and the environment that
produced it.  The ``results-gate`` CI job refuses pull requests that
change code or configs without a matching manifest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "SCHEMA_VERSION",
    "RunWriter",
    "git_info",
    "sha256_text",
    "sha256_file",
    "environment",
    "validate_manifest",
]

SCHEMA_VERSION = 1
_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "created_at",
    "status",
    "code_sha",
    "git_dirty",
    "config_path",
    "config_sha256",
    "seed",
    "environment",
    "metrics",
    "artifacts",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_info(repo_root: str | Path | None = None) -> tuple[str, bool]:
    """Return ``(head_sha, dirty)``; honours ``DES_CODE_SHA`` for synced copies."""
    override = os.environ.get("DES_CODE_SHA")
    root = Path(repo_root or Path(__file__).resolve().parents[2])
    try:
        sha = override or _run_git(root, "rev-parse", "HEAD")
        # Result artefacts are written before the manifest is finalised;
        # they must not make the run look dirty.
        dirty = bool(
            _run_git(root, "status", "--porcelain", "--", ".", ":(exclude)results/**")
        )
        return sha, dirty
    except (OSError, subprocess.CalledProcessError):
        return override or "unknown", True


def environment() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = torch.version.cuda
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
        else:
            info["gpu"] = None
    except Exception:  # pragma: no cover - torch is optional for pure helpers
        info["torch"] = None
        info["cuda"] = None
        info["gpu"] = None
    return info


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class RunWriter:
    """Create a result directory and its manifest.

    Parameters
    ----------
    stage_dir:
        Directory such as ``results/stage1``.  A run-specific
        subdirectory is created beneath it.
    config:
        Parsed experiment configuration.
    config_path:
        Repository-relative path of the config file.
    seed:
        Random seed used by the run.
    command:
        Exact command line, for reproduction.
    code_sha:
        Optional override; otherwise read from git.
    tags:
        Free-form labels (rounds, mode, model, ...).
    """

    stage_dir: Path
    config: Mapping[str, Any]
    config_path: str
    seed: int
    command: str
    code_sha: str | None = None
    repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    tags: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.stage_dir = Path(self.stage_dir)
        sha, dirty = git_info(self.repo_root)
        if self.code_sha:
            sha = self.code_sha
        self.code_sha = sha
        self.git_dirty = dirty
        self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        config_sha = sha256_text(_canonical_json(dict(self.config)))
        self.run_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"-{sha[:8]}-{config_sha[:8]}-s{self.seed}"
        )
        self.path = self.stage_dir / self.run_id
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "config.yaml").write_text(
            yaml.safe_dump(dict(self.config), sort_keys=False), encoding="utf-8"
        )
        self._log_path = self.path / "train.log"
        self._jsonl_path = self.path / "metrics.jsonl"
        self._best: dict[str, float] = {}
        self._log_lines: list[str] = []

    def log(self, message: str) -> None:
        self._log_lines.append(message)
        with open(self._log_path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    def record(self, step: int, metrics: Mapping[str, float]) -> None:
        finite = {
            key: float(value)
            for key, value in metrics.items()
            if isinstance(value, (int, float)) and math.isfinite(float(value))
        }
        payload = {"step": step, **finite}
        with open(self._jsonl_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        for key, value in finite.items():
            if value > self._best.get(key, -math.inf):
                self._best[key] = value

    def finish(
        self,
        *,
        status: str = "completed",
        final: Mapping[str, float] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        metrics = {
            "final": {k: float(v) for k, v in (final or {}).items()},
            "best": dict(self._best),
        }
        (self.path / "metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8"
        )
        artifacts = sorted(
            str(p.relative_to(self.path))
            for p in self.path.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        )
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "status": status,
            "code_sha": self.code_sha,
            "git_dirty": self.git_dirty,
            "config_path": self.config_path,
            "config_sha256": sha256_text(_canonical_json(dict(self.config))),
            "seed": self.seed,
            "command": self.command,
            "environment": environment(),
            "metrics": metrics,
            "artifacts": artifacts,
            "tags": dict(self.tags),
        }
        if extra:
            manifest.update(extra)
        (self.path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return manifest


def _collect_metrics(metrics: Mapping[str, Any]) -> list[tuple[str, Any]]:
    collected: list[tuple[str, Any]] = []
    for group in ("final", "best"):
        value = metrics.get(group)
        if isinstance(value, Mapping):
            collected.extend((f"{group}.{key}", item) for key, item in value.items())
    return collected


def validate_manifest(manifest: Mapping[str, Any], *, config_bytes: bytes | None = None) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        if field_name not in manifest:
            problems.append(f"missing field: {field_name}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("status") not in {"completed", "failed", "aborted"}:
        problems.append("status must be completed, failed or aborted")
    if not isinstance(manifest.get("code_sha"), str) or not manifest.get("code_sha"):
        problems.append("code_sha must be a non-empty string")
    if not isinstance(manifest.get("git_dirty"), bool):
        problems.append("git_dirty must be a boolean")
    if manifest.get("git_dirty"):
        problems.append("results were produced from a dirty working tree")

    metrics = manifest.get("metrics")
    if not isinstance(metrics, Mapping):
        problems.append("metrics must be an object")
    else:
        for key, value in _collect_metrics(metrics):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                problems.append(f"metric {key} is not a finite number: {value!r}")

    if config_bytes is not None:
        declared = manifest.get("config_sha256")
        if not isinstance(declared, str):
            problems.append("config_sha256 must be a string")
        else:
            try:
                parsed = yaml.safe_load(config_bytes)
                actual = sha256_text(_canonical_json(parsed))
            except yaml.YAMLError as exc:
                problems.append(f"config.yaml is not valid YAML: {exc}")
            else:
                if actual != declared:
                    problems.append(
                        f"config_sha256 mismatch: manifest={declared[:12]} file={actual[:12]}"
                    )
    return problems


def update_latest(results_root: str | Path, run_dir: str | Path, manifest: Mapping[str, Any]) -> Path:
    """Point ``results/LATEST.json`` at ``run_dir``."""
    root = Path(results_root)
    run_path = Path(run_dir)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "path": str(run_path.relative_to(root)).replace(os.sep, "/"),
        "code_sha": manifest["code_sha"],
        "created_at": manifest["created_at"],
        "metrics": manifest.get("metrics", {}),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    target = root / "LATEST.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target

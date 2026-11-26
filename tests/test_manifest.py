import json
from pathlib import Path

import pytest

import des_ml.manifest as manifest_module
from des_ml.manifest import RunWriter, validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_git(monkeypatch):
    monkeypatch.setattr(manifest_module, "git_info", lambda root=None: ("a" * 40, False))


def test_writer_produces_valid_manifest(tmp_path, fake_git):
    writer = RunWriter(
        stage_dir=tmp_path / "stage1",
        config={"rounds": 4, "mode": "kpa", "train": {"steps": 10}},
        config_path="configs/x.yaml",
        seed=0,
        command="python train.py",
        repo_root=REPO_ROOT,
        tags={"rounds": 4},
    )
    writer.record(1, {"val_acc": 0.5, "val_auc": 0.5})
    writer.record(2, {"val_acc": 0.75, "val_auc": 0.8})
    result = writer.finish(status="completed", final={"val_acc": 0.75})

    loaded = json.loads((writer.path / "manifest.json").read_text())
    assert result["code_sha"] == "a" * 40
    assert loaded["metrics"]["best"]["val_acc"] == pytest.approx(0.75)
    assert validate_manifest(loaded) == []
    assert (writer.path / "config.yaml").exists()
    assert (writer.path / "metrics.json").exists()
    assert "metrics.jsonl" in loaded["artifacts"]


def test_validator_rejects_missing_fields():
    problems = validate_manifest({"schema_version": 1})
    assert any("missing field" in problem for problem in problems)


def test_validator_rejects_non_finite_metric(fake_git):
    manifest = {
        "schema_version": 1,
        "run_id": "x",
        "created_at": "2026-01-01T00:00:00Z",
        "status": "completed",
        "code_sha": "a" * 40,
        "git_dirty": False,
        "config_path": "configs/x.yaml",
        "config_sha256": "b" * 64,
        "seed": 0,
        "environment": {},
        "metrics": {"final": {"val_acc": float("nan")}, "best": {}},
        "artifacts": [],
    }
    problems = validate_manifest(manifest)
    assert any("finite" in problem for problem in problems)


def test_writer_refuses_to_overwrite(tmp_path, fake_git, monkeypatch):
    monkeypatch.setattr(manifest_module, "datetime", _FixedDatetime)
    first = RunWriter(
        stage_dir=tmp_path,
        config={"a": 1},
        config_path="c.yaml",
        seed=0,
        command="x",
        repo_root=REPO_ROOT,
    )
    first.finish(final={"val_acc": 0.1})
    with pytest.raises(FileExistsError):
        RunWriter(
            stage_dir=tmp_path,
            config={"a": 1},
            config_path="c.yaml",
            seed=0,
            command="x",
            repo_root=REPO_ROOT,
        )


class _FixedDatetime:
    @staticmethod
    def now(tz=None):
        import datetime as _dt

        return _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)

    strftime = staticmethod(lambda fmt: "20260101T000000Z")

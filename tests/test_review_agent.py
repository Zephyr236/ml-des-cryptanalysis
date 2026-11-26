import json
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import review_agent  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def completion(content: str) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ]
    }


def test_validate_base_url_requires_opencode_host(monkeypatch):
    assert review_agent.validate_base_url("https://opencode.ai/inference/go/openai/v1")
    with pytest.raises(RuntimeError):
        review_agent.validate_base_url("https://evil.example/v1")
    monkeypatch.setenv("OPENCODE_ALLOW_CUSTOM_BASE_URL", "1")
    assert review_agent.validate_base_url("https://proxy.internal/v1")
    with pytest.raises(RuntimeError):
        review_agent.validate_base_url("http://proxy.internal/v1")


def test_call_opencode_headers_payload_and_parse(monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(completion('{"summary":"ok","verdict":"sound","findings":[]}'))

    monkeypatch.setattr(review_agent.urllib.request, "urlopen", fake_urlopen)
    text = review_agent.call_opencode("review this", "deepseek-v4.1-flash", "session-1", "test-key")

    assert json.loads(text)["verdict"] == "sound"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["headers"]["x-opencode-session"] == "session-1"
    assert captured["headers"]["user-agent"] == "ml-des-review/1.0"
    assert captured["payload"]["model"] == "deepseek-v4.1-flash"
    assert captured["payload"]["max_tokens"] == review_agent.OPENCODE_MAX_TOKENS
    system_prompt = captured["payload"]["messages"][0]["content"]
    assert review_agent.NO_TOOL_NOTE in system_prompt
    assert review_agent.TOOL_NOTE not in system_prompt


def test_call_opencode_retries_transient_http_error(monkeypatch):
    calls = {"count": 0}

    def fake_urlopen(request, timeout=0):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, None)
        return FakeResponse(completion('{"summary":"ok","verdict":"sound","findings":[]}'))

    monkeypatch.setattr(review_agent.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(review_agent.time, "sleep", lambda _: None)
    text = review_agent.call_opencode("x", "m", "s", "k")
    assert "ok" in text
    assert calls["count"] == 2


def test_call_opencode_rejects_truncated_nonempty_content(monkeypatch):
    def fake_urlopen(request, timeout=0):
        return FakeResponse(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"role": "assistant", "content": '{"summary": "partial"'},
                    }
                ]
            }
        )

    monkeypatch.setattr(review_agent.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="truncated"):
        review_agent.call_opencode("x", "m", "s", "k")


def test_select_backend_by_credentials():
    assert review_agent.select_backend("opencode", "", "") == "opencode"
    assert review_agent.select_backend("", "anthropic", "") == "claude"
    assert review_agent.select_backend("", "", "oauth") == "claude"
    assert review_agent.select_backend("", "", "") == "none"
    # OpenCode wins when both are present; there is no runtime fallback.
    assert review_agent.select_backend("opencode", "anthropic", "oauth") == "opencode"


def test_build_prompt_includes_metrics_and_pr_metadata(monkeypatch, tmp_path):
    run = tmp_path / "results" / "stage1" / "run-1"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "code_sha": "a" * 40,
                "git_dirty": False,
                "config_sha256": "b" * 64,
                "seed": 0,
                "status": "completed",
                "tags": {"split": "splitmix64-v1"},
                "metrics": {"final": {"mean_rank": 32.5}, "best": {"top1": 0.01}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_agent, "REPO_ROOT", tmp_path)
    prompt = review_agent.build_prompt(
        "diff --git a/x b/x",
        {"title": "T", "head_sha": "abc123", "base_sha": "def456", "body": "body"},
    )
    assert "metrics_final" in prompt
    assert "metrics_best" in prompt
    assert "head_sha: abc123" in prompt
    assert "splitmix64-v1" in prompt


def test_format_comment_names_backend():
    text = review_agent.format_comment(
        {"summary": "ok", "verdict": "sound", "findings": []}, 7, "OpenCode Zen Go / deepseek-v4.1-flash"
    )
    assert "OpenCode Zen Go / deepseek-v4.1-flash" in text
    assert "PR #7" in text

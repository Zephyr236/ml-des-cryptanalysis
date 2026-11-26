import io
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

    monkeypatch.setattr(review_agent._OPENER, "open", fake_urlopen)
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

    monkeypatch.setattr(review_agent._OPENER, "open", fake_urlopen)
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

    monkeypatch.setattr(review_agent._OPENER, "open", fake_urlopen)
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
        "diff --git a/results/stage1/run-1/manifest.json b/results/stage1/run-1/manifest.json\n",
        {"title": "T", "head_sha": "abc123", "base_sha": "def456", "body": "body"},
    )
    assert "metrics_final" in prompt
    assert "metrics_best" in prompt
    assert "head_sha: abc123" in prompt
    assert "splitmix64-v1" in prompt
    assert '"changed_by_pr": true' in prompt


def test_format_comment_names_backend():
    text = review_agent.format_comment(
        {"summary": "ok", "verdict": "sound", "findings": []}, 7, "OpenCode Zen Go / deepseek-v4.1-flash"
    )
    assert "OpenCode Zen Go / deepseek-v4.1-flash" in text
    assert "PR #7" in text


def test_cross_origin_redirect_refused():
    import urllib.request

    handler = review_agent._SameOriginRedirect()
    request = urllib.request.Request(
        "https://opencode.ai/inference/go/openai/v1/chat/completions",
        headers={"Authorization": "Bearer secret"},
    )
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/v1")


def _event(tmp_path, number=7):
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": number,
                    "title": "T",
                    "body": "body",
                    "head": {"sha": "a" * 40},
                    "base": {"sha": "b" * 40, "ref": "main"},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _set_github_env(monkeypatch, tmp_path, event):
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    diff = tmp_path / "pr.diff"
    diff.write_text("diff --git a/x b/x\n", encoding="utf-8")
    monkeypatch.setenv("PR_DIFF_PATH", str(diff))


def test_main_dry_run_without_credentials_does_not_post(monkeypatch, tmp_path):
    for key in (
        "OPENCODE_ZEN_API_KEY",
        "OPENCODE_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py", "--dry-run"])
    posted = []
    monkeypatch.setattr(review_agent, "post_comment", lambda *a, **k: posted.append(a))
    assert review_agent.main() == 0
    assert posted == []


def test_main_selects_opencode_and_posts(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-key")
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    monkeypatch.setattr(
        review_agent,
        "call_opencode",
        lambda *a, **k: '{"summary":"ok","verdict":"sound","findings":[]}',
    )
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "OpenCode Zen Go" in posted[-1]


def test_main_without_credentials_posts_skip(monkeypatch, tmp_path):
    for key in (
        "OPENCODE_ZEN_API_KEY",
        "OPENCODE_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "skipped" in posted[-1].lower()


def test_main_disables_claude_without_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_TOOL_TRANSPORT", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "skipped" in posted[-1].lower()
    assert "ALLOW_TOOL_TRANSPORT" in posted[-1]


def test_main_allows_claude_with_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("ALLOW_TOOL_TRANSPORT", "1")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])

    async def fake_agent(prompt, model):
        return '{"summary":"ok","verdict":"sound","findings":[]}'

    monkeypatch.setattr(review_agent, "run_agent", fake_agent)
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "Claude Agent SDK" in posted[-1]


def test_main_dry_run_disables_claude_without_posting(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_TOOL_TRANSPORT", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py", "--dry-run"])
    posted = []
    monkeypatch.setattr(review_agent, "post_comment", lambda *a, **k: posted.append(a))
    assert review_agent.main() == 0
    assert posted == []


def test_main_disables_claude_even_with_opt_in_on_untrusted_event(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("ALLOW_TOOL_TRANSPORT", "1")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "workflow_dispatch" in posted[-1]


def test_main_disables_claude_with_opt_in_and_empty_event(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("ALLOW_TOOL_TRANSPORT", "1")
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    posted = []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    assert review_agent.main() == 0
    assert "workflow_dispatch" in posted[-1]


def _research_review() -> dict:
    return {
        "summary": "A research change with a measurable claim.",
        "verdict": "needs-work",
        "research_analysis": {
            "research_content": True,
            "hypothesis": "A 4-round KPA scorer has signal.",
            "design": "Key-disjoint splits, 64 pairs; no budget-matched baseline yet.",
            "results": "The metric is at chance; the negative is not yet controlled.",
            "missing_analyses": ["Budget-matched random search", "Rank diagnostic"],
            "next_experiments": ["Run the DDT rank with a real characteristic"],
            "confidence": "medium",
        },
        "findings": [],
        "recommendations": [
            {
                "priority": "high",
                "kind": "experiment",
                "title": "Add a budget-matched baseline",
                "detail": "Compare against random search at the same key-trial budget.",
            }
        ],
    }


def test_format_comment_includes_research_analysis():
    text = review_agent.format_comment(_research_review(), 7, "OpenCode Zen Go / test")
    assert "## Research analysis" in text
    assert "**Hypothesis:**" in text
    assert "**Missing analyses:**" in text
    assert "Budget-matched random search" in text
    assert "Add a budget-matched baseline" in text
    assert "## Code findings" in text
    assert "No code findings." in text


def test_research_report_body_includes_sections():
    body = review_agent.research_report_body(
        _research_review(), 7, "TH-1 trail search", "a" * 40, "OpenCode Zen Go / test"
    )
    assert "Research analysis — PR #7" in body
    assert "TH-1 trail search" in body
    assert "Missing analyses" in body
    assert "Rank diagnostic" in body
    assert "Add a budget-matched baseline" in body


def test_is_research_diff():
    def diff(path):
        return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"

    assert review_agent.is_research_diff(diff("src/des_ml/des.py"))
    assert review_agent.is_research_diff(diff("configs/eval/x.yaml"))
    assert review_agent.is_research_diff(diff("results/stage1/run/manifest.json"))
    assert review_agent.is_research_diff(diff("src/des_ml/des.py").replace("+++ b/src/des_ml/des.py", "+++ /dev/null"))
    assert not review_agent.is_research_diff(diff("docs/REVIEW-AGENT.md"))
    assert not review_agent.is_research_diff(diff(".github/workflows/ci.yml"))


def test_create_or_comment_issue_retries_without_labels(monkeypatch):
    monkeypatch.setattr(review_agent, "find_existing_issue", lambda *a, **k: None)
    calls = []

    def fake_github_json(url, token, method="GET", payload=None):
        calls.append((url, method, payload))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                url, 422, "Unprocessable", {}, io.BytesIO(b'{"errors":[{"field":"labels"}]}')
            )
        return {}

    monkeypatch.setattr(review_agent, "github_json", fake_github_json)
    review_agent.create_or_comment_issue("o/r", "t", "title", "body", ["missing-label"])
    assert len(calls) == 2
    assert "labels" in calls[0][2]
    assert "labels" not in calls[1][2]


def test_file_research_report_uses_research_labels(monkeypatch):
    captured = {}

    def fake_create(repo, token, title, body, labels):
        captured.update(title=title, labels=labels, body=body)

    monkeypatch.setattr(review_agent, "create_or_comment_issue", fake_create)
    review_agent.file_research_report(
        "o/r", "t", 7, "TH-1", "a" * 40, _research_review(), "backend"
    )
    assert captured["title"] == "[research] PR #7 analysis"
    assert "research-review" in captured["labels"]
    assert "analysis" in captured["labels"]


def test_main_files_research_report_for_research_diff(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    (tmp_path / "pr.diff").write_text(
        "diff --git a/src/des_ml/des.py b/src/des_ml/des.py\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    monkeypatch.setattr(
        review_agent, "call_opencode", lambda *a, **k: json.dumps(_research_review())
    )
    posted, reports, recommendations = [], [], []
    monkeypatch.setattr(
        review_agent, "post_comment", lambda repo, number, token, body: posted.append(body)
    )
    monkeypatch.setattr(
        review_agent,
        "file_research_report",
        lambda repo, token, number, title, sha, review, backend: reports.append(number),
    )
    monkeypatch.setattr(
        review_agent,
        "file_recommendation",
        lambda repo, token, rec, number, title: recommendations.append(rec["title"]),
    )
    assert review_agent.main() == 0
    assert posted
    assert reports == [7]
    assert recommendations == ["Add a budget-matched baseline"]


def test_find_existing_issue_is_unlabeled_and_paginates(monkeypatch):
    filler = [{"number": n, "title": f"other-{n}"} for n in range(100)]
    pages = {
        1: filler,
        2: [
            {
                "number": 200,
                "title": "Target Title",
                "user": {"login": "github-actions[bot]"},
                "body": "",
            }
        ],
    }

    def fake_github_json(url, token, method="GET", payload=None):
        page = int(url.split("&page=")[1].split("&")[0])
        return pages.get(page, [])

    monkeypatch.setattr(review_agent, "github_json", fake_github_json)
    found = review_agent.find_existing_issue("o/r", "t", "target title")
    assert found["number"] == 200


def test_parse_json_rejects_non_object():
    with pytest.raises(ValueError):
        review_agent.parse_json("[1, 2, 3]")


def test_format_comment_tolerates_malformed_shapes():
    review = {
        "summary": "",
        "verdict": "sound",
        "research_analysis": ["not", "a", "dict"],
        "findings": "not a list",
        "recommendations": [1, {"priority": "high", "kind": "experiment", "title": "T", "detail": "D"}],
    }
    text = review_agent.format_comment(review, 1, "backend")
    assert "No code findings." in text
    assert "T" in text
    assert "Recommendation details" in text


def test_create_or_comment_issue_raises_non_label_422(monkeypatch):
    monkeypatch.setattr(review_agent, "find_existing_issue", lambda *a, **k: None)
    calls = []

    def fake_github_json(url, token, method="GET", payload=None):
        calls.append(payload)
        raise urllib.error.HTTPError(
            url, 422, "Unprocessable", {}, io.BytesIO(b'{"message":"Validation Failed"}')
        )

    monkeypatch.setattr(review_agent, "github_json", fake_github_json)
    with pytest.raises(urllib.error.HTTPError):
        review_agent.create_or_comment_issue("o/r", "t", "title", "body", ["label"])
    assert len(calls) == 1


def test_find_existing_issue_ignores_human_issue(monkeypatch):
    human = {
        "number": 1,
        "title": "Target Title",
        "user": {"login": "alice"},
        "body": "human issue",
    }

    monkeypatch.setattr(
        review_agent, "github_json", lambda url, token, method="GET", payload=None: [human]
    )
    assert review_agent.find_existing_issue("o/r", "t", "target title") is None


def test_find_existing_issue_matches_bot_issue(monkeypatch):
    bot = {
        "number": 2,
        "title": "Target Title",
        "user": {"login": "github-actions[bot]"},
        "body": "",
    }

    monkeypatch.setattr(
        review_agent, "github_json", lambda url, token, method="GET", payload=None: [bot]
    )
    assert review_agent.find_existing_issue("o/r", "t", "target title")["number"] == 2


def test_main_skips_report_when_research_content_false(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    _set_github_env(monkeypatch, tmp_path, _event(tmp_path))
    (tmp_path / "pr.diff").write_text(
        "diff --git a/src/des_ml/des.py b/src/des_ml/des.py\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["review_agent.py"])
    review = _research_review()
    review["research_analysis"]["research_content"] = False
    monkeypatch.setattr(review_agent, "call_opencode", lambda *a, **k: json.dumps(review))
    monkeypatch.setattr(review_agent, "post_comment", lambda *a, **k: None)
    reports = []
    monkeypatch.setattr(
        review_agent,
        "file_research_report",
        lambda *a, **k: reports.append(a),
    )
    monkeypatch.setattr(review_agent, "file_recommendation", lambda *a, **k: None)
    assert review_agent.main() == 0
    assert reports == []


def test_research_report_body_tolerates_malformed_fields():
    review = {
        "summary": ["not", "a", "string"],
        "verdict": "sound",
        "research_analysis": {
            "research_content": True,
            "hypothesis": ["list"],
            "design": None,
            "results": 3,
            "missing_analyses": "not a list",
            "next_experiments": [1, 2],
            "confidence": "low",
        },
        "findings": "bad",
        "recommendations": [{"priority": "low", "kind": "code", "title": ["t"], "detail": None}],
    }
    body = review_agent.research_report_body(review, 1, "title", "sha", "backend")
    assert "Hypothesis" in body
    assert "Recommendation" in body

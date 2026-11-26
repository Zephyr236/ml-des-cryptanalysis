# Advisory review agent

The `code-review` workflow runs an LLM reviewer on every pull request. It
is **advisory**: it posts a comment, files `agent-review` issues for
high/medium findings, and never blocks a merge (ADR-0003).

## Transports

| Credential | Transport | Default model | Tools |
|---|---|---|---|
| `OPENCODE_ZEN_API_KEY` | OpenCode Zen Go, OpenAI-compatible | `deepseek-v4.1-flash` | none; diff + manifest summaries in the prompt |
| `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` | Claude Agent SDK | `claude-sonnet-5-5` | Read / Grep / Glob |

The transport is chosen by which credential exists; OpenCode wins when
both are present. There is no automatic fallback on error: a failed call
posts a non-blocking notice.

## Security model

The workflow uses `pull_request_target` and checks out the **base**
commit. The PR head is fetched only to build a diff with `git diff`; no
file from the PR is executed. This keeps the API key out of reach of
PR-controlled code. The base URL must be `https://opencode.ai/...` unless
`OPENCODE_ALLOW_CUSTOM_BASE_URL=1` opts into a proxy, and cross-origin
redirects are refused so the bearer token is never forwarded.

The tool-enabled Claude transport is **disabled on untrusted events**
(an allowlist: local runs and `workflow_dispatch` only): Read/Grep/Glob
plus an untrusted diff would let a prompt injection read files outside
the repository and repeat them in a comment. PR reviews use the
tool-less OpenCode transport. On an untrusted event with only Claude
credentials, a `--dry-run` exits without posting.

The tool-less transport cannot read files, but injected diff text can
still shape the wording of the public comment. Treat every review as
advisory and check its claims against the deterministic gates.

Manifest metrics are claims, not verified facts. The `results-gate`
independently checks the manifest schema, `code_sha`, config hash and a
clean tree; the reviewer must not treat `changed_by_pr` as proof of a
result.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OPENCODE_BASE_URL` | `https://opencode.ai/inference/go/openai/v1` | Go endpoint |
| `OPENCODE_MODEL` | `deepseek-v4.1-flash` | model id |
| `OPENCODE_MAX_TOKENS` | `64000` | output budget; reasoning consumes most of it |
| `REVIEW_MODEL` | `claude-sonnet-5-5` | Claude transport model |

Set the secret with `gh secret set OPENCODE_ZEN_API_KEY -R <owner>/<repo>`.
Never commit the key.

## Local dry-run

```bash
GITHUB_REPOSITORY=owner/repo GITHUB_TOKEN=dummy \
GITHUB_EVENT_PATH=/tmp/event.json PR_DIFF_PATH=/tmp/pr.diff \
OPENCODE_ZEN_API_KEY=... python scripts/ci/review_agent.py --dry-run
```

`/tmp/event.json` needs `pull_request.number`; `--dry-run` prints the
parsed JSON and posts nothing. The prompt includes the diff (truncated at
90k characters), PR metadata, and manifest summaries. A manifest is
marked `changed_by_pr` only when the PR touches it; new manifests are
visible in the diff.

## Failure policy

Any transport or parse error is caught, a short notice is posted, and the
step exits 0. The deterministic gates (`ci`, `results-gate`, `issue-gate`,
`adr-guard`, `adr-numbers`, `link-check`, `release-blockers`) remain the
authority.

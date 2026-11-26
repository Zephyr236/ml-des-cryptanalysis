# 0003. Advisory LLM review agent in CI

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236, Claude Code

## Context

The project has one human researcher and several AI agents. Code review
is the step most likely to be skipped, and the review that matters is
not style: it is methodology (leakage, baselines, statistics, compute
accounting, overclaiming). A deterministic linter cannot check those.

At the same time, an LLM's judgement is not a precise predicate. Making
it a required status check would let a hallucinated objection block a
correct merge, and would teach the researcher to bypass the gate.

The owner asked for a review agent built with the **Claude Agent SDK**
that reviews both code and training methodology and files its findings
as issues.

## Decision

1. `.github/workflows/code-review.yml` runs
   [`scripts/ci/review_agent.py`](../../scripts/ci/review_agent.py) on
   every `pull_request` event.
2. The agent is built with `claude-agent-sdk` (Python) and the Claude
   Code CLI installed in the runner.
3. **It can only comment and open issues.** The job is
   `continue-on-error: true`, the script always exits 0, and the check
   is deliberately absent from branch protection. This mirrors the
   delivery-gates principle: blocking is reserved for checks with an
   exact failure reason.
4. **Read-only tools only.** The SDK is configured with
   `allowed_tools=["Read", "Grep", "Glob"]`. It cannot run shell
   commands, edit files, or read repository secrets.
5. **Prompt injection is assumed.** The diff and repository content are
   untrusted. The system prompt says so explicitly; the tool allow-list
   is the actual boundary.
6. **Findings become issues.** High and medium findings are filed with
   the `agent-review` label and an area label (`crypto`, `leakage`,
   `statistics`, `training`, `compute`, `reproducibility`, `claims`,
   `code`). Duplicate titles reuse the open issue and append a comment.
7. **Missing credentials skip, not fail.** If neither
   `ANTHROPIC_API_KEY` nor `CLAUDE_CODE_OAUTH_TOKEN` is configured, the
   job posts a notice and exits successfully.
8. **Model is configurable** through `REVIEW_MODEL`; the default is
   `claude-sonnet-5-5`.

## Consequences

- Every PR gets a second reader at the cost of one API call per push.
  Synchronize events can be frequent; the `concurrency` group cancels
  superseded reviews.
- False positives are expected. They become issues, not blockers, and
  can be closed with a one-line rationale.
- The agent cannot verify claims that require running training. It can
  check that a manifest exists and that its metrics support the PR's
  sentences, but the scientific judgement remains human.
- The repository must hold an API key as an Actions secret. That key is
  never exposed to the agent's tools; only the SDK process reads it.

## Alternatives considered

- **Use the Anthropic Python SDK directly.** Simpler, but the owner
  explicitly asked for the Claude Agent SDK, and the agent benefits from
  repository-reading tools.
- **Make the review a required check.** Rejected: an LLM cannot state
  an exact failure predicate, and a hallucinated veto would be worse
  than no review.
- **Run the review only on demand.** Rejected: the reviews that get
  skipped are exactly the ones on rushed PRs.

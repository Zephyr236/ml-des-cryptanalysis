# 0001. Repository governance and delivery gates

- **Status:** Accepted
- **Date:** 2026-11-26
- **Deciders:** Zephyr236 (research owner), Claude Code (implementation agent)

## Context

This is a solo research project assisted by AI agents. The failure mode
we care about is not a missed deadline but a **claim that cannot be
reproduced**: a number in a README that no committed code, config or run
can regenerate. The previous stage of the work already produced one such
number (~27% at 2 rounds) without a split-by-key protocol or a committed
manifest.

We also want the process itself to be inspectable: every change arrives
as a pull request, every experiment is tied to an issue, and no agent
can quietly move `main`.

## Decision

1. **`main` is protected.** No direct pushes, no force-pushes, no
   deletion, linear history, squash merges only, conversation
   resolution required, and the protection applies to administrators.
2. **Required status checks:** `ci`, `adr-guard`, `adr-numbers`,
   `link-check`, `release-blockers`, `results-gate`, `issue-gate`.
3. **Issue gate.** A PR must close at least one issue (`Closes #N`) or
   carry `No-Issue: <reason>`. Any issue referenced with `Refs #N` must
   already be closed. No open issue labelled `blocker` may exist at
   merge time. This is stricter than GitHub's native "linked issue"
   support, which is why it is a repository script rather than a
   branch-protection setting.
4. **Results gate.** A PR that changes code or configs must add or
   update `results/**/manifest.json` whose `code_sha` is a commit in
   the PR, and must update `results/LATEST.json`. Documentation-only
   work may use `Results-Exempt: <reason>`.
5. **ADR gate.** Watched paths (`src/**`, `configs/**`, `scripts/**`)
   require an ADR under `docs/adr/`, enforced by
   [`chohan-sarmad-ali/delivery-gates`](https://github.com/chohan-sarmad-ali/delivery-gates)
   (ADR Guard, ADR number collision, link check, release blockers).
6. **The LLM review agent is advisory.** It comments and files issues,
   but is not a required check. Blocking is reserved for checks whose
   failure reason can be stated exactly (see ADR-0003).
7. **Bootstrap exception.** The repository's first commit was created
   before branch protection existed so that the protection itself could
   be configured. After that commit, the rules above apply without
   exception.

## Consequences

- Merging is slower: a one-line config change needs an ADR, a run
  manifest and a closed issue. This is intentional; it is the cost of
  making a negative result trustworthy.
- The issue gate can be gamed with a throwaway issue. That is accepted:
  the gate is a forcing function for writing down hypotheses, not a
  security boundary.
- Squash merging keeps `main` linear and makes `code_sha` in manifests
  easy to trace.
- Agents must learn the workflow from [`AGENTS.md`](../../AGENTS.md);
  the rules are not discoverable from GitHub settings alone.

## Alternatives considered

- **GitHub-native branch protection only.** Cannot express "all
  referenced issues closed" or "a manifest must match this PR".
- **CODEOWNERS + human review.** A solo project has no second reviewer;
  the LLM agent fills the "second reader" role, but only as advice.
- **A single mega-gate script.** Rejected: a failing mega-gate gives no
  precise reason, which is exactly the property the delivery-gates
  author argues against.

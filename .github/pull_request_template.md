## Summary

<!-- What changed and why. One paragraph is enough. -->

## Linked issues

<!-- A merge requires at least one closed issue. Use Closes #N. -->

Closes #

## Results

<!--
Every code/config PR must add results/<stage>/<run_id>/ and update
results/LATEST.json. Paste the run_id and the headline metrics below.
Documentation-only PRs may write: Results-Exempt: <reason>
-->

- run_id:
- manifest:
- headline metrics:
- data complexity (pairs × keys):
- compute (DES-encryption equivalents):

```
Results-Exempt: <!-- reason, if applicable -->
```

## Risk

<!-- What could break, what is the rollback, what remains unverified. -->

## Decision record

<!-- ADR added/updated, or ADR-Exempt: <reason> -->

## Checklist

- [ ] Tests added or updated for new logic
- [ ] `pytest -q` passes locally or in CI
- [ ] Experiment was run on the GPU host, not on the controller
- [ ] `manifest.json` has `git_dirty: false` and a `code_sha` in this PR
- [ ] `results/LATEST.json` updated
- [ ] No secrets, tokens or passwords in the diff
- [ ] Claims in this description are supported by the attached metrics
- [ ] Review-agent issues (high/medium) answered or filed as follow-ups

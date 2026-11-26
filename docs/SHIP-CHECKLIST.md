# Ship checklist

The `release-blockers` gate fails while any item marked **BLOCKER** (in
the item or its heading, or marked with ⛔) is unchecked. Ordinary
unchecked items are ignored on purpose: a checklist you cannot merge
against until every box is ticked stops being written honestly.

**No BLOCKER items are declared yet.** Before a release, promote the
items that must hold for that release; until then this file documents
readiness without blocking day-to-day work.

## Stage 0 — infrastructure

- [x] Reference DES passes the FIPS test vector
- [x] Round-reduced DES round-trips for every round count 1–16
- [x] PyTorch DES matches the reference implementation
- [x] Key-disjoint 80/10/10 split implemented and tested
- [x] Result manifest schema and validator implemented
- [x] Seven blocking CI gates wired
- [x] Advisory review agent wired (Claude Agent SDK)
- [x] Branch protection enabled on `main` (admins enforced; direct push rejected)
- [x] GPU host bootstrap reproduced from `scripts/remote/bootstrap.ps1`
- [x] First GPU smoke run executed on the host and committed

## Stage 1 — distinguisher

- [ ] 4-round KPA distinguisher beats the shuffled-label control
- [ ] 4-round CPA distinguisher beats the classical differential baseline
- [ ] Advantage curve measured for 4, 6, 8, 10 rounds
- [ ] Three seeds per configuration

## Stage 2 — key recovery

- [ ] Last-round subkey ranking implemented for all eight S-boxes
- [ ] Success verified by real re-encryption, not by network score
- [ ] Budget-matched random-search baseline reported
- [ ] Data complexity reported in known/chosen pairs

## Stage 3–4 — scaling and boundary

- [ ] 12/14/16-round negative results recorded with a rank diagnostic
- [ ] Compute compared with `2^56` brute force in encryption equivalents

## Release blockers (template)

The gate parses checklist syntax even inside HTML comments, so this
section deliberately contains **no** checkbox lines until a release is
being prepared. When that happens, add items in this form:

`- [ ] BLOCKER: <condition that must hold for this release>`

Example conditions for the first paper release: every experiment in
`docs/EXPERIMENTS.md` has a committed manifest; no open issue labelled
`blocker`; the report has been signed by the research owner.

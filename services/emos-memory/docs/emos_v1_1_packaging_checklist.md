# EMOS v1.1 Packaging Checklist

## Goal

This checklist defines the final bundle composition for `EMOS v1.1`.

## Package Composition

- [ ] README is present and matches package identity
- [ ] API reference is present and matches runtime/report contract shape
- [ ] handoff manual is present and matches receiver sequence
- [ ] acceptance walkthrough is present and matches acceptance wording
- [ ] acceptance checklist is present and matches package identity
- [ ] final delivery manifest is present and matches artifact map
- [ ] acceptance evidence bundle is present
- [ ] known limitations note is present
- [ ] release notes are present

## Artifact Composition

- [ ] delivery-pack JSON is present
- [ ] delivery-pack Markdown is present
- [ ] storage backup artifact is present
- [ ] storage recovery guidance is present
- [ ] migration/rollback guidance is present
- [ ] long-horizon evidence directory is present
- [ ] demo-run summary path is present

## Validation Composition

- [ ] test suite passes
- [ ] smoke passes
- [ ] integration flows pass
- [ ] delivery-pack generation passes
- [ ] delivery demo passes

## Final Packaging Rule

- Treat the package as complete only when documentation, artifacts, and validation evidence all point to the same reproducible release posture.

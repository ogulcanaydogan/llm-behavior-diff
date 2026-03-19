# Release Notes Draft — Phase 8B Stabilization

## Highlights
- Added and stabilized adapter expansion path with explicit model routing support in core flow.
- Kept deterministic final decision policy with optional metadata-only judge signal.
- Extended significance reporting to:
  - run-level bootstrap + Wilson intervals
  - compare-level bootstrap delta CI + permutation p-values
- Upgraded HTML reporting experience (interactive self-contained explorer).
- Standardized local parity workflow:
  - `make install-dev`
  - `make ci-local`
  - `make release-local`

## Breaking changes
- None.

## Developer migration notes
- Prefer project-local `.venv` flow over system Python installs.
- Use `make ci-local` as the pre-PR gate and `make release-local` for package readiness checks.

## CI/Release readiness
- Core quality checks aligned with local parity commands.
- Package build + twine check + wheel smoke validated.

## Known non-blocking warnings
- Build emits setuptools deprecation warnings around license metadata format.
- Functional output is unaffected; a packaging hardening follow-up is tracked separately.

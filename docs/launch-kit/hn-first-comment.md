# HN First Comment

Thanks for checking this out.

A few transparent notes for context:

- Final regression/improvement decisions are deterministic and comparator-first.
- `--judge-model` is implemented as optional metadata-only signal.
- Judge runs only on semantic-diff tests, is non-fatal on errors, and never overrides final deterministic flags.
- Run metadata includes bootstrap + Wilson intervals; compare includes bootstrap delta CI and permutation p-values.
- Factual checks are heuristic/deterministic (no external fact API in this version).

What I optimized for:

1. reproducible upgrade checks
2. explainable decisions with comparator breakdowns
3. CI-ready JSON artifacts for gating and audit

Known gaps still planned:

- broader adapter ecosystem beyond current OpenAI/Anthropic/LiteLLM/local routing
- advanced statistical methods beyond bootstrap/Wilson/permutation
- richer visual reporting surface

If you run model-upgrade gates in production, I’d value specifics on:

- your regression thresholds
- required sign-off metadata
- failure policy defaults (strict fail-fast vs continue-on-error)

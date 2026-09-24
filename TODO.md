# Known limitations and open items

> **No release blockers are outstanding.** Everything the paper claims is
> released and independently verified; an external auditor reproduced the
> headline result, both principal tables, and all six held-out router rows from
> the released data. This file is the honest list of what is *not* done, so that
> a reader can judge the artifact's edges rather than discover them. It is not a
> defect report.

Completed work is not recorded here — see `CHANGELOG.md` for what exists and
`docs/provenance/` for how each number was verified.

## Resolved during assembly

Recorded so the trail is visible, not because anything is pending: the
NonCommercial benchmark was excluded from every artifact and the exclusion was
verified; the per-problem post-answer probe predictions were recovered and now
reproduce the headline exactly; and the two OmniMath scoring passes were
reconciled to 3 problems, with the camera-ready scoring shipped. See
`docs/provenance/`.

## Near-term

These do not affect any scientific claim in the paper.

- **Per-problem token costs for nine of the ten settings.** We publish
  protocol-level token totals for OmniMath / gpt-oss-120b only. The other nine
  settings have no released per-problem cost column. These must **not** be
  back-filled from another trace collection whose `total_tokens` counts a single
  model call rather than every call in the protocol — those figures differ from
  the paper's accounting by roughly 5x and would silently contradict Table 1.
  Recovering them means re-deriving from the original per-run cost manifests.

- **26 OmniMath problems absent from the cost table.** They fall in 13
  duplicate-text groups where a cost row cannot be attributed to a specific
  problem identifier. They are omitted rather than guessed. Resolving this needs
  a stable identifier in the original cost manifests.

- **The post-answer confidence probe cannot be fully re-run from released
  artifacts.** The probe consumes the model's own Baseline final answer, and that
  answer string was not persisted for the three gpt-oss-120b runs (recoverable
  for 6,462 of 12,928 probe rows: 100% of the Gemma settings, 0% of the gpt-oss
  settings). The probe's *outputs and metrics* are fully released and
  independently reproducible; only re-executing the probe is blocked.

- **Upstream revision pinning is incomplete.** LAB-Bench is pinned to a specific
  upstream revision. The other three benchmarks are identified by repository and
  version but not by content hash.

- **No model snapshot was version-pinned at run time.** We can name the model
  identifiers but not the exact served weights. This is why the artifact claims
  functional rather than bit-for-bit reproducibility.

- **AUPRC tie handling.** The published AUPRC column was computed with an
  average-precision function that does not break ties, and the probe emits
  integer confidences, so scores are heavily tied (30 distinct values across
  4,181 rows in one setting; 11 across 733 in another). The published digits
  are therefore order-dependent at the fourth decimal for large targets, and
  by more than a tenth for the smallest ones. Every AUROC is unaffected and
  reproduces exactly. Future work should report AUPRC with an explicit
  tie-handling policy, or avoid it for low-prevalence targets. See
  `docs/provenance/auprc_tie_handling.md`.

- `docs/reproduction/paper_artifact_matrix.csv` names `make reproduce-tables`
  as the generating command for more tables than that script actually rebuilds.
  The script regenerates the two matched-outcome tables (plus the interaction
  table behind a flag); the confidence, router, and primary-split tables are
  published as verified aggregates but have no one-command regeneration path in
  this repository yet.

- No checked-in expected-output fixture exists for the router path, so router
  training is not regression-tested against a frozen expectation. It is
  verified against the released predictions instead.

- **Only the metadata-only router has a published checkpoint.** The main
  text+metadata router and the six-setting variants were not serialized at
  training time; their per-problem predictions, hyperparameter searches and
  metrics are released, and the training code reproduces them, but there is no
  saved estimator to download. Re-fitting and publishing those checkpoints is
  straightforward and not yet done.

- The published checkpoint is a scikit-learn pickle fitted under 1.8.0. It emits
  `InconsistentVersionWarning` on other versions, and `predict_proba` raises on
  at least 1.6.1 while `predict` works. A version-independent format (skops, or
  exported coefficients) would be a more durable artifact.

- Expand the fixture suite so more of the analysis path is covered without a
  data download.

## Long-term

- Additional solver families beyond the two studied here.
- **Repeated stochastic runs per problem-protocol pair.** Every published
  interval measures benchmark-problem sampling, not run-to-run variability,
  because each pair has exactly one realized outcome. Repeated sampling is the
  single most valuable extension to this dataset.
- Task domains beyond competition mathematics, biology, and broader science.
- Learned routers that beat the reported oracle gaps, which remain 18.5-28.9
  points on the six evaluated settings.
- Independent evaluator audits, including human adjudication of a sample of
  automatic correctness verdicts.
- Complete raw traces, if upstream licenses and storage permit.
- Cost models beyond logged tokens: latency, price, energy, and parallelism.

---

These are open problems and possible directions, not commitments made by the
paper.

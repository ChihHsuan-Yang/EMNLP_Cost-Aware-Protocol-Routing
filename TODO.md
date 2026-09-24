# TODO

Scope note: this file lists work that is *not* done. Completed work is not
recorded here — see `CHANGELOG.md` and `docs/provenance/` for what exists.

## Release blockers

*None outstanding at the time of publication.* Items that were blocking during
assembly (excluding the NonCommercial benchmark from every artifact; recovering
the per-problem post-answer probe predictions; resolving the two OmniMath
scoring passes) were resolved and verified; see `docs/provenance/`.

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

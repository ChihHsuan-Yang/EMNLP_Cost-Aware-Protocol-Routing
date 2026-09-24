# Changelog

All notable changes to this research artifact are documented here.
This project uses date-based versioning.

## [1.0.0] - 2026-09-23

First public release, accompanying the EMNLP 2026 camera-ready paper
*LLMs Can Predict Failure Risk, But Struggle to Predict Which Collaboration
Protocol Pays Off: Cost-Aware Protocol Routing Across Reasoning Tasks*
([arXiv:2608.14927](https://arxiv.org/abs/2608.14927)).

### Added

- Matched four-protocol per-problem outcomes for all **10** model-condition
  settings (15,088 rows), with fixed-order oracle labels.
- Post-answer confidence probe predictions for the **6** evaluated settings
  (12,928 rows), the injection-hardened probe prompt, and parse metadata.
- Held-out router evaluations for the 6 eligible settings, on identical held-out
  problem identifiers across routers, with split assignments.
- PER-versus-Broadcast interaction analyses, including the conditional subsets.
- The eight camera-ready aggregate tables under `results/aggregate/`.
- The `protocol_routing` analysis package, with offline reproduction of the
  paper's principal tables and figures.
- Protocol execution code with configurable OpenAI-compatible providers and a
  deterministic mock backend for offline end-to-end runs.
- Provenance records mapping every paper claim to its source artifact.
- The trained metadata-only router checkpoint, with its fitted feature builders,
  an explicitly verified label map, held-out predictions, and a runnable
  offline example.
- Project website and full reproduction guide.

### Verified at release

- All 10 settings reproduce the published coverage and oracle-distribution
  tables exactly, with the oracle recomputed from scratch.
- The headline result reproduces from raw per-problem probe predictions:
  4,151 parseable of 4,181, failure AUROC 0.8847.
- All 6 held-out router rows reproduce exactly.
- Label leakage, private-path, and secret scans pass, each proven able to fail
  against deliberately planted violations.

### Known limitations

See [`TODO.md`](TODO.md) and [`docs/limitations.md`](docs/limitations.md). In
brief: per-problem token costs are released for one of ten settings; the
post-answer probe cannot be re-executed from released artifacts because Baseline
answer strings were not persisted for the gpt-oss runs; no model snapshot was
version-pinned, so the artifact supports functional rather than bit-for-bit
reproduction.

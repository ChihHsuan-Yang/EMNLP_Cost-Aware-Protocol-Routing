# Paper-to-code matrix

Every principal table and figure in the paper, with the public data it comes
from, the command that regenerates it, what to expect, and how far the result
is allowed to drift before it counts as a failure.

`PER_PROBLEM_VERIFIED` means the published number was re-derived from released
per-problem data during release preparation. `AGGREGATE_ONLY` means the
aggregate is published and trustworthy, but a lower-level artifact needed to
re-derive it independently is not available; those are listed in `TODO.md`.

Bootstrap confidence intervals are **not** expected to match exactly: they are
2,000-resample problem-level percentile intervals and the endpoints move in the
fourth decimal with the resampling seed. Point estimates are checked strictly.


## Table 1 (representative routing policies)

- **Paper section:** Section 2 (Task and setup)
- **Released result file:** `results/aggregate/main_routing_heldout.csv`
- **Command:** `make reproduce-tables`
- **Input data:** OmniMath primary held-out split (n=423)
- **Model / condition:** gpt-oss-120b — competition_math
- **Policy or protocol:** Baseline; Tier-majority; frozen LLM router; frozen LLM router with cost prompt; Self-confidence gate; Fixed-order oracle
- **Compute / runtime:** laptop CPU, < 1 min
- **Expected output:** `results/paper_tables/main_routing_heldout.csv`
- **Expected metric:** Baseline 56.3 / gate 78.0 / oracle 92.4 solve percent
- **Tolerance:** exact on point estimates; CI endpoints +/- 0.01 absolute
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** Primary split is stratified 80/10/10 seed 42. Frozen-LLM rows traced to specific runs: 73.8/71.3k = merged frozen-router run v2 (built from a serial run plus a remaining-ids run, then a 73-problem retry merge; 60 of 423 problems still ended in fallback); 78.3/88.6k = the numeric-cost few-shot run. Per-problem predictions exist for both. Derives from the earlier OmniMath scoring pass; see docs/provenance/.

## Table 2 (failure score on increasingly specific targets)

- **Paper section:** Section 4 (Mechanism)
- **Released result file:** `results/aggregate/failure_and_protocol_value_targets.csv`
- **Command:** `make reproduce-tables`
- **Input data:** OmniMath and LAB-Bench (6 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — competition_math / llm_strict / text_no_tool
- **Policy or protocol:** post-answer confidence score vs 4 targets
- **Compute / runtime:** laptop CPU, < 2 min
- **Expected output:** `results/paper_tables/failure_and_protocol_value_targets.csv`
- **Expected metric:** gpt-oss OmniMath: Baseline-failure AUROC 0.8847 AUPRC 0.8950; any-collaboration AUPRC 0.7683; PER AUPRC 0.1674; Broadcast-only AUPRC 0.1041
- **Tolerance:** exact on AUROC/AUPRC to 4 dp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** This is the title claim. Reproduced by the release lead from raw per-problem probe predictions.

## Table 3 (matched solve and coverage)

- **Paper section:** Section 4 (Mechanism)
- **Released result file:** `results/aggregate/matched_protocol_coverage.csv`
- **Command:** `make reproduce-tables`
- **Input data:** all 4 benchmarks / 5 conditions (10 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — all five prompt conditions
- **Policy or protocol:** Baseline; Single; PER; Broadcast; fixed-order oracle
- **Compute / runtime:** laptop CPU, < 1 min
- **Expected output:** `results/paper_tables/matched_protocol_coverage.csv`
- **Expected metric:** 40 solve-rate cells + 10 oracle-coverage cells
- **Tolerance:** exact to 2 dp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** All 10 settings reproduce exactly from released per-problem matched labels with the oracle recomputed from scratch.

## Figure 1 (oracle labels by tier; extra cost vs extra gain)

- **Paper section:** Section 2 (Task and setup)
- **Released result file:** `docs/assets/figures/fig1_main_combined.png`
- **Command:** `make reproduce-figures`
- **Input data:** OmniMath primary split
- **Model / condition:** gpt-oss-120b — competition_math
- **Policy or protocol:** fixed-order oracle
- **Compute / runtime:** laptop CPU, < 2 min
- **Expected output:** `results/figures/fig1_main_combined.png`
- **Expected metric:** fractions sum to 1 within each tier
- **Tolerance:** visual + underlying CSV exact
- **Status:** `AGGREGATE_ONLY`
- **Notes:** Panel (a) oracle labels by difficulty tier; panel (b) extra cost against extra solve gain.

## Figure 2 (matched benchmarks breadth)

- **Paper section:** Section 4 (Mechanism)
- **Released result file:** `docs/assets/figures/fig2_matched_benchmarks.png`
- **Command:** `make reproduce-figures`
- **Input data:** all 10 settings
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — all five prompt conditions
- **Policy or protocol:** four protocols + oracle
- **Compute / runtime:** laptop CPU, < 2 min
- **Expected output:** `results/figures/fig2_matched_benchmarks.png`
- **Expected metric:** matches matched_protocol_coverage.csv
- **Tolerance:** underlying values exact to 2 dp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** Protocol hue with value-dependent tint across the 10 paired settings.

## Post-answer confidence metrics

- **Paper section:** Appendix (additional analyses)
- **Released result file:** `results/aggregate/postanswer_confidence.csv`
- **Command:** `make reproduce-tables`
- **Input data:** OmniMath and LAB-Bench (6 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — competition_math / llm_strict / text_no_tool
- **Policy or protocol:** post-answer probe
- **Compute / runtime:** laptop CPU, < 3 min
- **Expected output:** `results/paper_tables/postanswer_confidence.csv`
- **Expected metric:** parse rates; failure AUROC; ECE; Brier; mean confidence when correct vs wrong
- **Tolerance:** point estimates exact to 4 dp; bootstrap CI endpoints +/- 0.002
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** Headline: 4151 parseable of 4181, AUROC 0.8847, 95% CI [0.8732, 0.8955].

## Held-out router evaluation

- **Paper section:** Appendix (additional analyses)
- **Released result file:** `results/aggregate/heldout_router_evaluation.csv`
- **Command:** `make reproduce-tables`
- **Input data:** OmniMath and LAB-Bench (6 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — competition_math / llm_strict / text_no_tool
- **Policy or protocol:** Baseline; text+metadata router; Tier-majority; fixed-order oracle
- **Compute / runtime:** laptop CPU, < 5 min
- **Expected output:** `results/paper_tables/heldout_router_evaluation.csv`
- **Expected metric:** n; baseline/router/oracle solve; oracle gap; oracle-label macro F1; route distribution
- **Tolerance:** exact to 4 dp on solve rates
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** Stratified 70/15/15 by oracle label, seed 20260712, hyperparameters on dev only then refit on train+dev. All routers scored on identical held-out problem ids (verified).

## Paired router differences

- **Paper section:** Appendix (additional analyses)
- **Released result file:** `results/aggregate/heldout_router_paired_differences.csv`
- **Command:** `make reproduce-tables`
- **Input data:** OmniMath and LAB-Bench (6 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — competition_math / llm_strict / text_no_tool
- **Policy or protocol:** router minus Tier-majority; router minus Baseline
- **Compute / runtime:** laptop CPU, < 5 min
- **Expected output:** `results/paper_tables/heldout_router_paired_differences.csv`
- **Expected metric:** paired deltas in percentage points with 95% CIs
- **Tolerance:** point estimates exact to 0.1 pp; CI endpoints +/- 0.5 pp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** 2000-resample paired problem-level bootstrap.

## PER vs Broadcast interaction

- **Paper section:** Appendix (additional analyses)
- **Released result file:** `results/aggregate/per_broadcast_interaction.csv`
- **Command:** `python scripts/analyze_protocol_interactions.py`
- **Input data:** OmniMath and LAB-Bench (6 settings)
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — competition_math / llm_strict / text_no_tool
- **Policy or protocol:** PER vs Broadcast conditional on Baseline and Single both failing
- **Compute / runtime:** laptop CPU, < 2 min
- **Expected output:** `results/paper_tables/per_broadcast_interaction.csv`
- **Expected metric:** PER and Broadcast solve rates; Broadcast-minus-PER gap with CI; PER-only / Broadcast-only / both / neither counts
- **Tolerance:** exact on counts; gap +/- 0.05 pp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** The published table is the both-failed conditional subset. The source also carries all / baseline-failed / confidence-gate subsets.

## Oracle label distribution

- **Paper section:** Appendix (additional analyses)
- **Released result file:** `results/aggregate/oracle_label_distribution.csv`
- **Command:** `make reproduce-tables`
- **Input data:** all 10 settings
- **Model / condition:** gpt-oss-120b and Gemma-4-31B-it — all five prompt conditions
- **Policy or protocol:** fixed-order oracle
- **Compute / runtime:** laptop CPU, < 1 min
- **Expected output:** `results/paper_tables/oracle_label_distribution.csv`
- **Expected metric:** Baseline / Single / PER / Broadcast / None percentages per setting
- **Tolerance:** exact to 2 dp
- **Status:** `PER_PROBLEM_VERIFIED`
- **Notes:** Recomputed from matched labels in the fixed order.

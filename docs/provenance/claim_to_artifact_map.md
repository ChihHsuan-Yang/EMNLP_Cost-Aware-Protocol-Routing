# Claim-to-Artifact Map

Agent A, 2026-09-23. Every table and figure in the camera-ready paper
(`paper.tex` → `sections/*.tex`), mapped to its aggregate CSV, per-problem
source, generating script, and run id / commit.

**Status legend**

- **VERIFIED** — I traced the chain to a per-problem artifact on disk this session,
  or hash-matched the aggregate to its originating commit.
- **INFERRED** — the chain is consistent and the inputs exist, but one link
  (usually the exact script invocation or a `.tex`-hardcoded number's producer)
  was not confirmed.
- **UNRESOLVED** — a required artifact is missing; named explicitly.

**Path shorthand**

- `<CR>` = `<camera-ready>`
- `<RB>` = `<post-review-extract>` (git `096e3621`, branch `emnlp-trace2training-rebuttal-2026-07-14`)
- `<ML>` = `<RB>/results_2026-07-12/tables/matched_labels`
- `<AU>` = `<hpc-runs>` — post-answer confidence-probe outputs recovered from Aurora HPC (runs 2026-07-12 and 2026-07-13)
- `<AV>` = `<experiment-repo>/results/emnlp_routing` (branch `origin/codex/emnlp-short-routing`, head `430757aef362a541139628c088cedded0551b106`)
- `<HB>` = `<inventory-repo>/dhd-release-worktree/results/emnlp_routing` — the tree `make_paper_figures.py` actually reads (`ROOT`, lines 42–45). Its `benchmark/routing_benchmark.csv` is byte-identical to `<AV>`'s (same sha256), i.e. a mirror.

---

## Main paper

| # | Paper object | Aggregate CSV | Per-problem source | Generating script | Run id / commit | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Fig 1** `fig:motivation-tradeoff` (a) oracle labels by tier, (b) extra cost vs solve gain — `figures/main/fig1_main_combined.pdf` | `<HB>/model_comparison/story_analysis/oracle_label_distribution_by_tier.csv`; `<HB>/model_comparison/story_analysis/extra_cost_vs_extra_solve_gain.csv`; `<HB>/model_comparison/router_comparison_current.csv` | `<AV>/benchmark/routing_benchmark.csv` (4,181 rows) + `<AV>/splits/routing_splits.csv` | `<CR>/scripts/make_paper_figures.py::plot_fig1_combined` | `430757aef` (May-era scoring) | **VERIFIED** (all 3 inputs present; `ROOT` is `<HB>`) |
| 2 | **Table 1** `tab:main-routing` — 6 representative policies, n=423 | `<CR>/anc/main_routing_heldout.csv` | `<AV>/splits/routing_splits.csv` test split (423 rows) over `<AV>/benchmark/routing_benchmark.csv` | Values hardcoded in `sections/02_task.tex` ll. 65–70; inputs are `<HB>/heuristics/motivation_policy_table.csv`, `<HB>/model_comparison/router_comparison_current.csv`, `<HB>/metacognition/confidence_cascade/cascade_policy_results.csv` | `430757aef`, seed 42, 80/10/10 | **INFERRED** — the three inputs exist and the split is verified (see note A), but no script writes `anc/main_routing_heldout.csv`; it appears hand-assembled. |
| 3 | **Table 2** `tab:value-targets` — post-answer score on 4 targets, n=4,151 | `<CR>/anc/failure_and_protocol_value_targets.csv` (gpt-oss OmniMath rows); `<CR>/results/additional_analysis/confidence_value_targets.csv` | Targets from `<ML>/omnimath2__competition_math_4181__gpt_oss_120b.csv`; scores from `<AU>/run_20260713/results/full_p0_addon/omnimath2__competition_math_4181__gpt_oss_120b/predictions.jsonl` (4,181 rows) | `<RB>/scripts/score_confidence_probe.py`, then `verify_round2_results.py` | `096e3621`; bootstrap seed 20260712, 2,000 resamples | **VERIFIED** — see note B. Both halves are per-problem; I reproduced the heading AUROC 0.8847 exactly. |
| 4 | **Fig 2** `fig:matched-robustness` — 10 paired settings, 4 benchmarks — `figures/main/fig2_matched_benchmarks.pdf` | `<CR>/results/additional_analysis/aggregate_solve_oracle_coverage.csv` | `<ML>/*.csv` (10 of the 12 files) | `<CR>/scripts/make_paper_figures.py::plot_fig2_matched_benchmarks` | `096e3621` | **VERIFIED** — the only figure reading from `<CR>`. I re-derived all 5 rates × 10 settings against `anc/matched_protocol_coverage.csv`: 10/10 settings, 0 mismatches. |

---

## Appendix A — additional analyses (`appendix_additional_analyses.tex`)

| # | Paper object | Aggregate CSV | Per-problem source | Generating script | Run id / commit | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | **Table S1** `tab:routing-scope` — scope comparison | none (prose table) | n/a | hardcoded in `.tex` ll. 20–37 | n/a | **INFERRED** — descriptive, no numeric claim needing an artifact. |
| 6 | **Table S2** `tab:robustness-full-ci` — 10 settings, solve/coverage + 95% CI | `<CR>/anc/matched_protocol_coverage.csv`; CIs from `<CR>/results/additional_analysis/aggregate_solve_oracle_coverage.csv` | `<ML>/*.csv` (10 settings) | `<RB>/scripts/build_no_model_artifacts.py` | `096e3621`; seed 20260712, 2,000 resamples | **VERIFIED** — lead verified oracle recomputation from per-problem; I additionally hash-matched the aggregate to its `096e3621` original (identical). |
| 7 | **Table S3** `tab:robustness-oracle-labels` — oracle label distributions, 10 settings | `<CR>/anc/oracle_label_distribution.csv`; `<CR>/results/additional_analysis/oracle_label_distribution.csv` | `<ML>/*.csv` | `<RB>/scripts/build_no_model_artifacts.py` | `096e3621` | **VERIFIED** — aggregate hash-identical to `<RB>/results_2026-07-12/tables/oracle_label_distribution.csv`. |
| 8 | **Table S4** `tab:postanswer-confidence-all` — post-answer confidence, 6 settings | `<CR>/anc/postanswer_confidence.csv`; `<CR>/results/additional_analysis/confidence_probe_metrics.csv` | `<AU>/run_20260712/results/full_p{0,1}/<setting>/predictions.jsonl` + `<AU>/run_20260713/results/full_p0_addon/<setting>/predictions.jsonl` — all 6 settings; labels in `confidence_probe/P{0,1}/<setting>/labels_for_scoring.csv` | `<RB>/scripts/run_confidence_probe.py` → `score_confidence_probe.py` → `collect_confidence_metrics.py` | `096e3621`; Aurora jobs `jobs/p0_full.pbs`, `p1_full.pbs`, `gpt_oss_omni_confidence.pbs` | **VERIFIED** — I re-derived all 6 AUROCs and parse_rates from the raw predictions; every one matches to 4 dp. See note B. |
| 9 | **Table S5** `tab:value-targets-all` — 4 targets × 6 settings | `<CR>/anc/failure_and_protocol_value_targets.csv`; `<CR>/results/additional_analysis/confidence_value_targets.csv` | targets from `<ML>/*.csv`; scores from the same 6 recovered `predictions.jsonl` as #8 | `<RB>/scripts/verify_round2_results.py` | `096e3621` | **VERIFIED** — same recovered input as #8. Aggregate is hash-identical to `<RB>/results_2026-07-14/verification/confidence_value_targets.csv`. |
| 10 | **Table S6** `tab:heldout-router-all` — held-out router, 6 settings | `<CR>/anc/heldout_router_evaluation.csv`; `<CR>/results/additional_analysis/router_text_metadata_verification.csv` | `<RB>/results_2026-07-13/aurora_results/router_retraining_run2_all6/<setting>/test_predictions.csv` (6 settings) | `<RB>/scripts/train_rebuttal_routers.py`, verified by `verify_round2_results.py` | `096e3621`; stratified 70/15/15 by oracle label, seed 20260712 | **VERIFIED** — per-problem predictions present for all 6 settings, with `split_assignments.csv` alongside. |
| 11 | **Table S7** `tab:heldout-router-deltas` — paired deltas vs Tier-majority / Baseline | `<CR>/anc/heldout_router_paired_differences.csv`; `<CR>/results/additional_analysis/router_paired_delta_bootstrap.csv` | same `test_predictions.csv` as #10 | `<RB>/scripts/verify_round2_results.py` | `096e3621`; 2,000 resamples | **VERIFIED** — aggregate hash-identical to its `096e3621` original. |
| 12 | **Table S8** `tab:per-broadcast-key` — PER vs Broadcast conditional on Baseline+Single failing | `<CR>/anc/per_broadcast_interaction.csv`; `<CR>/results/additional_analysis/per_broadcast_bootstrap_conditional.csv` | `<ML>/*.csv` (6 settings) | `<RB>/scripts/verify_round2_results.py` | `096e3621`; 2,000 resamples | **VERIFIED** — conditioning subset is fully recomputable from the per-problem correctness flags; aggregate hash-identical. |

---

## Appendix B–F — primary-split analyses (`appendix.tex`)

All of these predate the post-review work and rest on the **May-era**
`routing_benchmark.csv` scoring, not the July matched labels. See note A.

| # | Paper object | Aggregate CSV | Per-problem source | Generating script | Run id / commit | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 13 | **Table S9** `tab:extended-routing` | `<CR>/results/table_s1_extended_routing.csv` | `<AV>/benchmark/routing_benchmark.csv` + `<AV>/splits/` test | `<AV>/../../emnlp_short_paper/scripts/build_router_result_catalog.py` | `430757aef` | **INFERRED** |
| 14 | **Table S10** `tab:main-bootstrap-ci` | `<CR>/results/table1_bootstrap_ci.csv` | same | `emnlp_short_paper/scripts/build_bootstrap_ci_tables.py` | `430757aef` | **INFERRED** |
| 15 | **Table S11** `tab:embedding-cost-prompt` | `<CR>/results/embedding_router_metrics.csv`; `<CR>/results/gpt_oss_120b_cost_prompt_metrics.csv` | `<AV>/embedding_router/`, `<AV>/api_router/` | `emnlp_short_paper/scripts/train_embedding_router.py`, `run_api_router.py` | `430757aef` | **INFERRED** |
| 16 | **Table S12** `tab:marginal-cost` | `<CR>/results/router_comparison_current.csv` | `<AV>/model_comparison/` | `emnlp_short_paper/scripts/build_model_comparison_report.py` | `430757aef` | **INFERRED** |
| 17 | **Table S13** `tab:router-token-sensitivity` | `<CR>/results/router_comparison_current.csv` | `<AV>/api_router/` | `build_model_comparison_report.py` | `430757aef` | **INFERRED** |
| 18 | **Table S14** `tab:no-tier-ablation` | `<CR>/results/table_s_no_tier_ablation.csv` | `<AV>/difficulty_metadata_ablation/` | `emnlp_short_paper/scripts/run_difficulty_metadata_ablation.py` | `430757aef` | **INFERRED** |
| 19 | **Table S15** `tab:source-holdout` | `<CR>/results/table_s_source_holdout_stress.csv` | `<AV>/source_holdout_stress/` | `emnlp_short_paper/scripts/run_source_holdout_stress.py` | `430757aef` | **INFERRED** |
| 20 | **Fig S3** `fig:supp-escalation` — `figS3_escalation_per_model.pdf` | `<HB>/metacognition/implicit_analysis/escalation_by_tier_per_model.csv` | `<AV>/heuristics/heuristic_predictions.csv` + api_router preds | `make_paper_figures.py::plot_figS3` | `430757aef` | **VERIFIED** (input present) |
| 21 | **Fig S5 a/b** `fig:supp-self-assessment` (`fig3a_reliability.pdf`, `fig3b_oracle_by_confidence.pdf`) | `<HB>/metacognition/direct_confidence/cleaned_by_claude/v3_complete_cleaned.csv` | same (per-problem, 423-split pre-answer probe) | `make_paper_figures.py::plot_fig3a`, `plot_fig3b` | `430757aef` | **VERIFIED** — per-problem file present. Note C. |
| 22 | **Table S16** `tab:preanswer-predictive` | `<CR>/results/table_s5c_q1_predictive_summary.csv` | `v3_complete_cleaned.csv` | `emnlp_short_paper/scripts/build_metacognition_analysis.py` | `430757aef` | **INFERRED** |
| 23 | **Table S17** `tab:gemma-actor-scope` — reduced Gemma-3 actor stack, tier-sampled 833 | `<CR>/results/additional_analysis/aggregate_solve_oracle_coverage.csv` row `omnimath2__tier_sampled_833__gemma3_27b` | `<ML>/omnimath2__tier_sampled_833__gemma3_27b.csv` (833 rows) | `<RB>/scripts/build_no_model_artifacts.py` | `096e3621`; endpoint `google/gemma-3-27b-it` | **VERIFIED** |
| 24 | **Fig S4** `fig:supp-cascade-knee` — `figS4_cascade_kneedle.pdf` | `<HB>/metacognition/confidence_cascade/cascade_threshold_sweep_dev.csv`; `cascade_kneedle_selection_results.csv` | `v3_complete_cleaned.csv` over dev split | `make_paper_figures.py::plot_figS4` | `430757aef` | **VERIFIED** (inputs present) |
| 25 | **Table S18** `tab:cascade-ci` | `<CR>/results/router_bootstrap_ci.csv` | `<AV>/metacognition/confidence_cascade/` | `emnlp_short_paper/scripts/build_confidence_cascade_analysis.py` | `430757aef` | **INFERRED** |
| 26 | **Table S19** `tab:cascade-missing` | `<CR>/results/router_bootstrap_ci.csv` | same | `build_confidence_cascade_analysis.py` | `430757aef` | **INFERRED** |
| 27 | **Table S20** `tab:protocol-value-probe` | `<CR>/results/protocol_value_policy_results.csv` | `<AV>/metacognition/protocol_value_probe/` | `emnlp_short_paper/scripts/run_protocol_value_probe.py`, `build_protocol_value_policy.py` | `430757aef` | **INFERRED** |
| 28 | **Table S21** `tab:preanswer-bias` | `<CR>/results/table_s5b_q1_bias_by_tier.csv` | `v3_complete_cleaned.csv` | `build_metacognition_analysis.py` | `430757aef` | **INFERRED** |
| 29 | **Table S22** `tab:confidence-composition` | `<CR>/results/table_s6_confidence_bin_composition.csv` | `v3_complete_cleaned.csv` | `build_metacognition_analysis.py` | `430757aef` | **INFERRED** |
| 30 | **Table S23** `tab:preanswer-coverage` | `<CR>/results/table_s5a_q1_coverage_summary.csv` | `v3_complete_cleaned.csv` | `build_metacognition_analysis.py` | `430757aef` | **INFERRED** |
| 31 | **Table S24** `tab:split-distribution` — split sizes + oracle-label % | `<AV>/splits/split_metadata.json` | `<AV>/splits/routing_splits.csv` (4,181 rows) | `emnlp_short_paper/scripts/make_splits.py` | `430757aef`, seed 42 | **VERIFIED** — I recomputed the test-split label counts (238/97/38/32/18, sum 423) against `split_metadata.json`: exact match. |
| 32 | **Table S25** `tab:protocol-reference` | `<CR>/results/table_s2_protocol_reference.csv` | `<AV>/benchmark/routing_benchmark.csv` test rows | `build_routing_benchmark.py` | `430757aef` | **INFERRED** |
| 33 | **Table S26** `tab:oracle-distribution` | `<CR>/results/table_s2b_oracle_label_distribution_test.csv` | `<AV>/splits/routing_splits.csv` test rows | `make_splits.py` | `430757aef` | **VERIFIED** — recomputed from the split file. |
| 34 | **Fig S1** `fig:supp-loss` — `figS1_loss_history.pdf` | `<HB>/text_metadata_router/loss_history.csv`; `<HB>/metadata_only_router/loss_history.csv` | training logs | `make_paper_figures.py::plot_figS1` | `430757aef` | **VERIFIED** (inputs present) |
| 35 | **Fig S6** `fig:supp-source` — `figS6_source_heatmap.pdf` | `<HB>/model_comparison/story_analysis/source_breakdown_top12.csv` | `<AV>/model_comparison/` | `make_paper_figures.py::plot_figS6` | `430757aef` | **VERIFIED** (input present) |
| 36 | **Fig S2** `figS2_solve_at_budget.pdf` (built but not `\includegraphics`'d in `paper.tex`) | `<HB>/model_comparison/story_analysis/solve_at_budget_curve.csv` | `<AV>/model_comparison/` | `make_paper_figures.py::plot_figS2` | `430757aef` | **VERIFIED** (input present); figure appears orphaned — confirm before shipping. |
| 37 | `figures/main/fig1a_*`, `fig1b_*`, `fig2_implicit_calibration.pdf` | various | — | `make_paper_figures.py` | `430757aef` | **INFERRED** — built but superseded by the combined Fig 1 / not referenced in `paper.tex`. Exclude from release or mark provisional. |

---

## Notes

### A. Two scorings underlie one paper

Table 1 and all of Appendix B–F derive from `<AV>/benchmark/routing_benchmark.csv`
(May-era, `baseline_llm` = 2,373). Fig 2 and Appendix A derive from `<ML>/*.csv`
(July, `baseline_llm` = 2,376 for the same gpt-oss OmniMath setting). I established
this by reading `<AV>/splits/split_metadata.json`, which names
`routing_benchmark.csv` as its input, and by summing `baseline_llm` across
`routing_splits.csv` → 2,373.

The two scorings differ on exactly **3 of 4,181** problems, one of which
(`tier09:86`) is in the Table-1 test split. Full analysis, including how the
join was established and why two candidate join keys were rejected, in
`discrepancies.md` §D1–D2. This does not invalidate anything, but the release must
state which artifact backs which table.

### B. The post-answer confidence probe IS per-problem reproducible (corrected)

**An earlier revision of this file said the opposite. It was wrong, and the way
it was wrong is worth recording.**

I searched `<research-root>` for `predictions.jsonl`, found none from
the probe runs, and reported that the artifact "does not exist anywhere" — while
quoting the Aurora an HPC project space path in the same paragraph. An Aurora PBS job
writes to the HPC filesystem; my search scope excluded exactly the location the
evidence pointed to. A negative from a search that cannot reach the likely
location is not a negative.

The files were recovered from Aurora and are now local under `<AU>`. Per-problem
predictions exist for **all six** confidence settings (4,181 / 4,181 / 741 / 741
/ 1,542 / 1,542 rows), each with `confidence`, `confidence_norm`, `parse_ok`,
`raw_text`, `rationale`, `repair_attempts` and `problem_uid`, and with the
scoring labels held in separate `labels_for_scoring.csv` files so the no-leakage
separation survives on disk.

I re-scored all six from raw with my own tie-averaged-rank AUROC. **Every
published AUROC and parse_rate reproduces exactly to four decimals**, and
independently reseeded 2,000-resample CIs agree to ~0.003. The headline setting:
4,151 parseable of 4,181 (0.9928), 1,802 positives, AUROC **0.8847**, CI
[0.8735, 0.8958] against the published [0.8732, 0.8955]. Full table in
`discrepancies.md` §D6.

Rows #3, #8 and #9 are therefore **VERIFIED**. The abstract's headline can be
re-bootstrapped, re-scored against other targets, and audited row by row.

One gap remains: the recovered post-answer predictions are **not yet staged**
into the public tree. What is currently at
`hf_dataset_staging/data/confidence/primary_omnimath_confidence_predictions.csv`
is 839 rows of the *pre-answer* primary-split probe — a different instrument.
Until the post-answer predictions are staged, the headline is reproducible by us
but not by a reader.

### C. Pre-answer vs post-answer probes are different instruments

`CAMERA_READY_AUDIT.md`'s terminology ledger distinguishes them, and the paper
keeps them apart (`04_mechanism.tex`: "The two results correspond to distinct
operating points and are not treated as replicates"). Concretely:

- **Pre-answer** (rows #21, #22, #28–30): original submission, 423-example test
  split, 329 usable estimates, 0.859 AUROC. Per-problem data **is** on disk
  (`v3_complete_cleaned.csv`). Reproducible.
- **Post-answer** (rows #3, #8, #9): post-review, full 4,181, 4,151 parseable,
  0.8847 AUROC. Per-problem data **is** on disk, recovered from Aurora (note B).
  Reproducible — I re-derived it this session.

Both are now reproducible, so the reason to keep them apart is no longer
reproducibility (my earlier framing) but measurement identity: different probe
prompt, different information available to the model, different n, different
operating point. The paper is careful here and the release must stay careful.

### D. `make_paper_figures.py` reads a third tree

`ROOT` is hardcoded to `<HB>` at lines 42–45 — neither the camera-ready tree nor
the AgentVerse tree named in the release brief. All 13 figure/table inputs it
references were confirmed present (see the `figroot__*` rows in
`source_inventory.csv`, all VERIFIED), and its `routing_benchmark.csv` is
byte-identical to `<AV>`'s. So it is a mirror, not a divergent result set — but
the path must be parameterized and those 13 tables shipped, or no figure except
Fig 2 is reproducible by a reader.

### E. Excluded benchmark: verification that it is absent from the release

Two *internal* intermediate tables used during the audit carry rows for a
benchmark that the paper excludes (12 settings rather than 10). That benchmark is
CC-BY-NC-SA-4.0 (NonCommercial) and has no matched Gemma run, so it is excluded
from the paper and from every released artifact.

Verified at release time: the excluded benchmark appears in **none** of the
shipped artifacts. The published aggregate tables contain no such row, and the
released per-problem table contains exactly 10 settings and 15,088 rows. The
intermediate tables that did carry it were audit inputs and are not published.
A CI test (`tests/test_no_private_paths.py`) fails the build if that benchmark
ever appears in a released file outside an explicit exclusion note.

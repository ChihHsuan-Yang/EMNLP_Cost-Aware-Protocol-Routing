# Discrepancies Between Candidate Release Artifacts

Agent A, 2026-09-23. Every number below was read from a file in this session.
All research repositories were treated as read-only.

---

## D1. routing_benchmark.csv vs camera-ready matched labels (gpt-oss OmniMath)

### Verdict

**Same underlying run, three problems re-scored.** These are not different runs
and not a different benchmark sample. Exactly **3 of 4,181** problems disagree,
all three in the same direction (the newer artifact marks Baseline *correct*
where the older marks it *incorrect*). The release must use the camera-ready
matched labels and say so.

### The two artifacts

| | Older (May-era) | Camera-ready |
| --- | --- | --- |
| Path | `<experiment-repo>/results/emnlp_routing/benchmark/routing_benchmark.csv` | `<post-review-extract>/results_2026-07-12/tables/matched_labels/omnimath2__competition_math_4181__gpt_oss_120b.csv` |
| sha256 | `5532231e8febb8137704db71af6f4acc5e57b75d05f888e734d62aa67876780f` | `61d8da85118e9a1a…` (per `no_model_manifest.json`) |
| mtime | 2026-05-27 | 2026-07-14 (git commit `096e3621`) |
| Rows | 4,181 | 4,181 |
| Problem id scheme | `tierNN:M` | `omni2_N` |

The identical file also exists at
`<inventory-repo>/dhd-release-worktree/results/emnlp_routing/benchmark/routing_benchmark.csv`
(same sha256) — it is one file, mirrored, not two runs.

### Aggregate gap

| Field | routing_benchmark.csv | matched_labels CSV | Delta |
| --- | ---: | ---: | ---: |
| `baseline` correct | 2,373 (56.7568%) | 2,376 (56.8285%) | **+3** |
| `single` correct | 3,295 | 3,294 | −1 |
| `per` correct | 3,561 | 3,561 | 0 |
| `broadcast` correct | 3,730 | 3,730 | 0 |
| oracle label `baseline_llm` | 2,373 | 2,376 | +3 |
| oracle label `single_agent` | 961 | 958 | −3 |
| oracle label `per` | 366 | 366 | 0 |
| oracle label `broadcast` | 175 | 175 | 0 |
| oracle label `none` / `unsolved` | 306 | 306 | 0 |

`anc/matched_protocol_coverage.csv` and `anc/oracle_label_distribution.csv` both
report `baseline_pct = 56.83` for gpt-oss OmniMath. 2376/4181 = 56.8285%, so the
camera-ready aggregates were produced from the **matched_labels** file, not from
`routing_benchmark.csv`. `routing_benchmark_metadata.json` independently records
`"label_counts": {"baseline_llm": 2373, …}` for the older artifact.

### Problem-level join

The two id schemes do not share a key. `problem_id` is `tierNN:M`; `problem_uid`
is `omni2_N` numbered 1..4428 with gaps (the raw Omni-MATH-2 file has 4,428 rows;
the filter keeps 4,181).

Two candidate crosswalks were tried and one was rejected:

- **Rejected:** `global_example_idx` in `routing_benchmark.csv` is a *within-tier*
  index (values 1..~1100 repeating across tiers), not a global key. Joining on it
  produced 709 spurious "disagreements" — an artifact of the wrong join, not data.
- **Rejected:** `source_problem_id` inside the trace `problem` dict is a
  *within-chunk* index (1..10). It collapses 4,181 rows onto 84 distinct targets.
- **Used:** normalized problem text. Extracted the `problem.problem` string from
  `hf_reorg2/baseline_llm/omnimath2/gpt_oss_120b/traces/records.jsonl` (4,181
  records, keyed by `problem_uid`), whitespace-normalized, SHA-1'd, and joined
  against the whitespace-normalized `problem` column of `routing_benchmark.csv`.
  Result: **4,168 distinct hashes on both sides, overlap 4,168 — a perfect
  bijection on text.** 13 hashes are shared by exactly 2 problems each
  (genuine duplicate problem statements in the upstream corpus), giving
  **4,155 unambiguous 1:1 pairs** plus 13 two-element groups.

Sanity check: the `gemma_4_31b` matched-labels file uses uid form `omni2:tNN:M`,
which converts to `tierNN:M` and matches the `routing_benchmark.csv` id set
**exactly** (4,181 = 4,181, zero on either side only). That independently
confirms both artifacts index the same 4,181-problem sample.

### The 3 disagreeing problems

Over the 4,155 unambiguous pairs:

| routing_benchmark `problem_id` | matched_labels `problem_uid` | old label | new label | flag changes |
| --- | --- | --- | --- | --- |
| `tier09:85` | `omni2_3997` | `single_agent` | `baseline_llm` | baseline False→1, single True→0 |
| `tier09:86` | `omni2_4006` | `single_agent` | `baseline_llm` | baseline False→1 |
| `tier08:37` | `omni2_94` | `single_agent` | `baseline_llm` | baseline False→1 |

Per-field disagreement totals across all 4,155 pairs: `baseline` 3, `single_agent` 1,
`per` 0, `broadcast` 0, oracle label 3. Written to
`_disagreements_gptoss.csv`.

For the 13 duplicate-text groups, the **label multiset matches in all 13**
(0 groups differ), so they contribute no disagreement either way.

3 (unambiguous) + 0 (ambiguous) = 3, which exactly accounts for the 2,373 → 2,376
aggregate gap. Nothing is unexplained.

### Interpretation

All three flips are Baseline `incorrect → correct` on hard-tier problems, with
PER and Broadcast untouched. That is the signature of a **re-scoring of Baseline
answers under a revised judge/parse path**, not a re-execution: a re-run would
perturb all four protocols and would not be confined to 3 rows. The `single`
flip on `tier09:85` is the downstream consequence of its Baseline flip under the
fixed-order oracle. I did **not** find a scoring-version field distinguishing the
two artifacts, so the *mechanism* is inferred from the pattern, not read from a
field — recorded as **UNRESOLVED (mechanism)**; the *count and identity* of the
differences are VERIFIED.

### Release action

Ship `matched_labels/*.csv` as the per-problem labels of record. `routing_benchmark.csv`
may still ship (it is the basis of the 423-problem split, see D2) but must be
labelled as the May-era scoring and must not be presented as the source of any
camera-ready percentage. A `KNOWN_DIFFERENCES` note naming these 3 problem ids
should travel with it.

---

## D2. Does the 423-problem primary split (Table 1) derive from routing_benchmark.csv or from matched_labels?

### Verdict: **routing_benchmark.csv.** Table 1 is on the older scoring.

Evidence:

- `splits/split_metadata.json` names its input explicitly:
  `"benchmark_path": ".../emnlp_short_paper/outputs/benchmark/routing_benchmark.csv"`,
  with `"seed": 42`, `"train_ratio": 0.8`, and `"split_counts": {"train": 3342, "dev": 416, "test": 423}`.
- `splits/routing_splits.csv` has 4,181 rows carrying a `cheapest_successful_protocol`
  column. Summing `baseline_llm` across all three splits gives **2,373** — the
  routing_benchmark number, not 2,376.
- The test split's label counts are `baseline_llm` 238, `single_agent` 97,
  `per` 38, `none` 32, `broadcast` 18 (sum 423), matching
  `split_metadata.json`'s `label_split_counts` test column exactly.
- Split ids are `tierNN:M`, the routing_benchmark scheme.

Consequence: **Table 1 (`anc/main_routing_heldout.csv`, n=423) and the
10-setting matched tables rest on two different scorings of the same gpt-oss
OmniMath run.** Of the 3 flipped problems, `tier09:86` is in the **test** split;
`tier09:85` and `tier08:37` are in **train**. So one of the 423 Table-1 test
problems carries a label the camera-ready matched tables would score
differently — a 1/423 = 0.24 pp perturbation, far inside Table 1's ~±4.5 pp
bootstrap intervals, but it should be stated rather than left for a reader to
find.

Recommended release wording: Table 1's split and labels come from the original
May-era benchmark build; the breadth tables come from the July matched-label
rebuild; the two differ on 3 of 4,181 problems, one of which is in the Table-1
test split.

---

## D3. SciBench: 574/571 rows on disk vs n=565 in the paper

`data/science-benchmarks/manifest.json` declares scibench
`"count": 580, "text_only_count": 574`. The README repeats 574. The on-disk
`scibench/text_only/all.jsonl` actually has **571** rows (the manifest's 574 is
itself stale by 3). The paper and `anc/matched_protocol_coverage.csv` report
**n=565**.

Resolved: the 565 matched uids are a strict subset of the 571 on-disk uids
(verified: subset = True). The 6 missing uids are
`scibench:thermo:1.3`, `scibench:thermo:1.6`, `scibench:thermo:2.13`,
`scibench:thermo:6.10`, `scibench:thermo:9.9`, `scibench:thermo:14.5`.
All six are from the `thermo` source. The reason they have no matched outcome is
**UNRESOLVED** — no exclusion audit naming them was found; `text_only/excluded_missing_artifact.jsonl`
holds the artifact-based exclusions, which are a different set. The release note
should state 565 as the matched-run n and list these 6 as unmatched, rather than
quoting the manifest's 574.

The 580 → 571 step *is* documented (6 artifact-dependent rows excluded, per the
README's conservative phrase filter); 580−6 = 574 is what the manifest expected,
so there is an additional undocumented −3 between the manifest and the file.

---

## D4. `make_paper_figures.py` reads from a third tree

`scripts/make_paper_figures.py` lines 42–45 hard-code:

```
ROOT = Path("<inventory-repo>/"
            "dhd-release-worktree/results/emnlp_routing")
```

This is neither the camera-ready tree nor the AgentVerse tree named in the
release brief. It exists locally and its `benchmark/routing_benchmark.csv` is
byte-identical to the AgentVerse copy (same sha256), so it is a mirror, not a
divergent result set. All 13 figure/table input files referenced from it were
confirmed present (see `source_inventory.csv`, `figroot__*` rows, all VERIFIED).

Only `fig2_matched_benchmarks.pdf` reads from the camera-ready tree
(`results/additional_analysis/aggregate_solve_oracle_coverage.csv`). Every other
figure depends on the `hub-MASTraceInventory` mirror. That path must be
parameterized before release, and the 13 input tables must be shipped, or the
figures are not reproducible by a reader.

Not a data contradiction — a reproducibility defect. Recorded here so it is not
lost.

---

## D5. Two settings present in internal artifacts are excluded from the paper and the release

`matched_labels/` holds 12 settings; the paper reports 10. The two extras are
`mascqa__text_only__gpt_oss_120b` (642 rows) and
`omnimath2__tier_sampled_833__gemma3_27b` (833 rows). `results/additional_analysis/aggregate_solve_oracle_coverage.csv`
likewise has 12 rows against the paper's 10.

This is deliberate and documented, not a discrepancy:
`CAMERA_READY_AUDIT.md` states "MaScQA is omitted from the release paper because
no matched Gemma run is available." The gemma3_27b row is the reduced actor-stack
check reported separately in the appendix (`tab:gemma-actor-scope`).

**But it is a licensing problem.** `data/science-benchmarks/manifest.json` marks
mascqa `"license": "CC-BY-NC-SA-4.0"`, `"release_compatibility": "internal_only_not_compatible_with_cc_by_sa_4_0_release"`.
The MaScQA row must be **dropped** from any released copy of
`aggregate_solve_oracle_coverage.csv` and `oracle_label_distribution.csv`, and
`mascqa__text_only__gpt_oss_120b.csv` must not ship. See `licenses.md`.

---

## D6. Post-answer confidence probe: per-problem artifact RECOVERED (corrects an earlier finding in this file)

**Status: RESOLVED. This section previously reported the opposite conclusion and was wrong.**

### What I originally wrote, and why it was wrong

An earlier revision of this file stated that no `predictions.jsonl` existed for
the post-answer probe, and that every post-answer number in the paper was
therefore AGGREGATE_ONLY and unrecoverable. That was a false negative.

The search behind it covered `<research-root>`. The probe was an
**Aurora PBS job**, and an Aurora job writes its outputs to the HPC filesystem
(`<hpc-project-space>/...`) — which that search
scope excluded by construction. I even quoted the flare path in the same
paragraph while concluding the artifact did not exist. A negative from a search
whose scope excludes the likely location is not a negative; it is an untested
hypothesis stated as a result.

The release lead recovered the files from Aurora. They are now on local disk.

### What is actually present

Per-problem `predictions.jsonl` exists for **all six** confidence settings:

| Setting | Path (under `<hpc-runs>`) | Lines |
| --- | --- | ---: |
| omnimath2 gpt-oss-120b | `run_20260713/results/full_p0_addon/omnimath2__competition_math_4181__gpt_oss_120b/` | 4,181 |
| omnimath2 Gemma-4-31B-it | `run_20260712/results/full_p0/omnimath2__competition_math_4181__gemma_4_31b/` | 4,181 |
| LAB-Bench strict Gemma | `run_20260712/results/full_p0/labbench__llm_strict__gemma_4_31b/` | 741 |
| LAB-Bench strict gpt-oss | `run_20260712/results/full_p0/labbench__llm_strict__gpt_oss_120b/` | 741 |
| LAB-Bench text-no-tool Gemma | `run_20260712/results/full_p1/labbench__text_no_tool__gemma_4_31b_text_no_tool/` | 1,542 |
| LAB-Bench text-no-tool gpt-oss | `run_20260712/results/full_p1/labbench__text_no_tool__gpt_oss_120b_text_no_tool/` | 1,542 |

Each record carries `problem_uid`, `example_id`, `confidence`,
`confidence_norm`, `parse_ok`, `parse_error`, `raw_text`, `rationale`,
`repair_attempts`, `latency_seconds`, `model`, `completed_at_utc`. Paired labels
live in separate `labels_for_scoring.csv` files under
`confidence_probe/P0|P1/<setting>/`, so the no-leakage separation is preserved
on disk.

### Independent re-derivation (all six settings)

I re-scored every setting from the raw predictions joined to its labels, with my
own AUROC implementation (tie-averaged ranks, score = 1 − `confidence_norm`,
target = Baseline fails):

| Setting | n | parseable | parse_rate | AUROC | published | reseeded 95% CI | published CI |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| omnimath2 gpt-oss | 4,181 | 4,151 | 0.9928 | **0.8847** | 0.8847 | [0.8735, 0.8958] | [0.8732, 0.8955] |
| omnimath2 Gemma | 4,181 | 4,178 | 0.9993 | **0.8012** | 0.8012 | [0.7871, 0.8157] | [0.7872, 0.8162] |
| LAB strict Gemma | 741 | 733 | 0.9892 | **0.8637** | 0.8637 | [0.8363, 0.8882] | [0.8359, 0.8894] |
| LAB strict gpt-oss | 741 | 719 | 0.9703 | **0.5814** | 0.5814 | [0.5440, 0.6202] | [0.5410, 0.6165] |
| LAB t-n-t Gemma | 1,542 | 1,542 | 1.0000 | **0.7337** | 0.7337 | [0.7123, 0.7543] | [0.7110, 0.7562] |
| LAB t-n-t gpt-oss | 1,542 | 1,510 | 0.9792 | **0.6069** | 0.6069 | [0.5790, 0.6330] | [0.5808, 0.6347] |

Every published AUROC and parse_rate reproduces **exactly to four decimals**.
CIs differ only in the third-to-fourth decimal, as expected from an independent
resample draw. For the headline setting I also confirm 1,802 positives
(prevalence 0.4341) and 30 unparseable, matching
`gpt_oss_omni_confidence_probe_verification.json` and the paper's Limitations.

### Consequence

All confidence-probe rows are **PER_PROBLEM_VERIFIED**, not AGGREGATE_ONLY. The
abstract's 0.8847 headline, Table `tab:postanswer-confidence-all`, and
Table `tab:value-targets` / `tab:value-targets-all` can all be re-bootstrapped,
re-scored against different targets, and audited row by row. Corrected in
`claim_to_artifact_map.md` (rows #3, #8, #9), in
`docs/provenance/post_review_to_release_map.csv` (PR-02, PR-03, PR-04), and in
`source_inventory.csv`.

### Residual gap (small, and real)

`hf_dataset_staging/data/confidence/primary_omnimath_confidence_predictions.csv`
is **839 rows** — the 423-test + 416-dev **pre-answer** primary-split probe. That
is a different instrument from the 4,181-row **post-answer** probe. The recovered
post-answer predictions are local but **not yet staged** into the public tree.
Staging them is what makes the paper's headline claim reproducible by a reader
rather than merely by us. Tracked as `VERIFIED_BUT_INCOMPLETE` in
`docs/provenance/code_extraction_map.csv`.

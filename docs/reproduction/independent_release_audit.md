# Independent Release Audit — EMNLP 2026 Cost-Aware Protocol Routing

**Auditor:** Sub-agent E (independent; did not build any part of this artifact)
**Date:** 2026-09-23
**Inputs used:** exactly two — a fresh clone of branch `public-release`, and a copy of the
dataset staging tree treated as the result of `hf download`. Nothing else was read.
**Workspace:** `/tmp/audit_e/` only.

---

## VERDICT: **SHIP WITH FIXES**

The science holds up. I independently re-derived the headline (0.8847 AUROC on
4,151/4,181), reproduced both principal aggregate tables to the last digit
(20/20 rows PASS), recomputed the fixed-order oracle on **all 15,088 rows with
zero mismatches**, reproduced all six held-out router rows exactly, and confirmed
the released feature files carry no label leakage by both name and value. The
camera-ready OmniMath rescoring is correctly in the data (2,376 = 56.83%, not the
May-era 2,373 = 56.76%). Security and privacy are clean across the full git history.

What blocks a clean ship is **packaging, not findings**. A newcomer who follows the
documented commands hits a failing test suite on the very first step, then finds
that two documented `make` targets do not exist, and then discovers that the
released data cannot be fed to the release's own reproduction tooling without
writing a schema adapter that no document describes. Separately, one published
column (AUPRC) does not reproduce from the released data by the repository's own
metric function.

All of these are fixable in a short pass. None of them is a reason to doubt the paper.

---

## Findings

| # | Sev | Finding | What I did / expected / happened | Evidence |
|---|-----|---------|----------------------------------|----------|
| 1 | **BLOCKER** | `make test` and `make smoke` fail on a fresh clone | Ran the README's own 3-command quickstart in order. Expected pass (README: "Every command above is exercised in CI"). Got 4 failures, exit code 2, on both targets. `tests/test_schema.py` requires keys `display_name`, `turns`, `stopping_rule`, `retry_policy`, `context_and_memory`, `final_answer_selection`, `evaluator_invocation`, `token_accounting`; the four protocol configs supply none of them — they use `name`, `max_rounds`, `rule`, `roles`, `provenance`. The test and the configs were written against different schemas. Since CI runs `pytest -q`, the README's Tests badge would be red. | `tests/test_schema.py:191`; `configs/protocols/{baseline,single,per,broadcast}.yaml`; `make test` → `MAKE_TEST_EXIT=2`, `4 failed, 202 passed` |
| 2 | **BLOCKER** | Released data cannot be consumed by the repo's own reproduction tooling | `docs/REPRODUCE.md` §6.3 and the Makefile both say `make reproduce-tables MATCHED_DIR=data/matched_labels`. The release ships **one combined file** `data/matched_labels.csv`, but `load_matched_dir()` globs `*.csv` in a **directory**, one file per setting, and requires columns `setting`, `problem_uid`, `model_endpoint`. The release provides `setting_id` and `problem_id`. No adapter, script, or doc describes the conversion — I searched the clone and the dataset docs. Track B, described as "the strong claim", is unreachable as documented. After I wrote my own 6-line adapter (split by setting; rename `setting_id`→`setting`, `problem_id`→`problem_uid`), everything passed perfectly. So this is packaging, not data. | `src/protocol_routing/matched.py:30-42,155-189`; `make reproduce-tables MATCHED_DIR=…/data/matched_labels` → `ERROR … Missing matched-label directory`; pointing at the real dir → `labels_for_scoring.csv: missing required columns ['setting','model_endpoint','problem_uid']` |
| 3 | **MAJOR** | Two documented `make` targets do not exist | README line 90 documents `make data`; `docs/REPRODUCE.md:119,235` documents `make validate-data` twice, including in Troubleshooting. Neither is a target. | `make -n data` → `No rule to make target 'data'`; `make -n validate-data` → same. Makefile `.PHONY` lists only help/setup/test/smoke/reproduce-tables/reproduce-figures/lint/clean |
| 4 | **MAJOR** | Published **AUPRC** column does not reproduce from released data | Every AUROC (24/24 targets across 6 settings) and every `positive_n`, `n_parseable` and `prevalence` reproduces exactly. AUPRC reproduces in **none** of the 6 settings, and the error changes sign (+0.0430 Gemma OmniMath, −0.0603 Gemma LAB-tnt, −0.0137 gpt-oss OmniMath), so it is not a tie-handling or estimator convention. The repo's own `confidence.auprc()` is plain `average_precision_score`, which yields 0.8813 / 0.7561 / 0.1648 / 0.1022 against the published 0.8950 / 0.7683 / 0.1674 / 0.1041. I also tried the trapezoidal PR variant: also no match. The paper's title claim is directional and survives (protocol-specific AUPRC collapses either way), but the exact published digits are currently not reproducible. | `src/protocol_routing/confidence.py:168-176`; `data/aggregate/failure_and_protocol_value_targets.csv`; my `auprc2.py` output showing all 6 settings X |
| 5 | **MAJOR** | `make setup` does not create an environment, contrary to the docs | `docs/REPRODUCE.md:65` — "`make setup` creates a virtual environment and installs the package." It runs only `python -m pip install -e ".[test]"`. On my machine bare `python` resolved to the user's global conda install, so following the docs would have installed the package and 24 dependencies into the user's global environment. I created a venv manually instead. | `Makefile:35-36`; `make -n setup` → `python -m pip install -e ".[test]"` |
| 6 | **MAJOR** | `docs/data_schema.md` is linked from the README but does not exist | README line 150 lists it under Documentation as "every column in every released table". The real schema doc lives inside the dataset (`docs/schema.md`), which a repo-only reader never sees. | `README.md:150`; `ls docs/data_schema.md` → No such file |
| 7 | **MAJOR** | `paper_artifact_matrix.csv` overstates what the tooling regenerates | 7 of 10 rows name `make reproduce-tables` as the generating command. That script rebuilds exactly **two** tables (`matched_protocol_coverage.csv`, `oracle_label_distribution.csv`), plus `per_broadcast_interaction.csv` behind `--include_optional`. `main_routing_heldout.csv`, `failure_and_protocol_value_targets.csv`, `postanswer_confidence.csv`, `heldout_router_evaluation.csv` and `heldout_router_paired_differences.csv` are **not** produced by it. Both figure rows name `make reproduce-figures`, which emits `fig_protocol_coverage.png` and `fig_oracle_label_distribution.png` — neither is `fig1_main_combined.png` or `fig2_matched_benchmarks.png`. Every row is nonetheless stamped `PER_PROBLEM_VERIFIED` (one `AGGREGATE_ONLY`). | `docs/reproduction/paper_artifact_matrix.csv`; `scripts/reproduce_paper_tables.py:38-45`; `ls /tmp/audit_e/out/tables` → 2 files |
| 8 | **MAJOR** | Leakage guard is defeatable by the `*_success` family — with **no rename trickery** | The guard's own tests honestly document that a *rename* to `feature_17` defeats it. But I found plainly-named outcome columns it does not catch: `baseline_success`, `per_success`, `broadcast_success`, `single_success`, `outcome`, `verdict`, `failed`, `is_failure`, `correctness`, `target`, `result`, `first_success_protocol`, `cheapest_protocol`, `y_true`. The patterns cover `*_correct`, `*_passed`, `*_solved`, `oracle*`, `gold*` but not `*_success`. I built a real feature frame carrying a verbatim copy of `baseline_correct` named `baseline_success` and it passed the guard with correlation **1.0** to the label. Adding `^.*_success$` and `^.*_failed$` to `FORBIDDEN_FEATURE_PATTERNS` closes most of it. **Note the released data is unaffected** — see Finding 15. | `src/protocol_routing/features.py:44-90`; my `attack.py`: `is_forbidden('baseline_success') = False`, smuggled-feature corr = 1.0 |
| 9 | MINOR | `docs/schema.md` makes a false statement about the 113 fallback rows | It says the fallback rows "still carry a `confidence_probability`, produced by the fallback path rather than a clean parse." In the released file all **113/113** test fallback rows have a **null** `confidence_probability`. The counts it gives (113/423 test, 109/416 dev) are exactly right; only the "still carry a value" clause is wrong. | `data/docs/schema.md:342-348`; 113 of 113 null |
| 10 | MINOR | `confidence_probability` is on a 0–100 scale despite its name and declared type | The name and `schema.json` (`"type": "number"`) both imply a probability. Values run 7.0–98.0. A reader applying the documented gate `confidence >= 70` as a probability gets 60.76%; on the correct scale (and treating nulls as escalate) it reproduces the published **78.01% vs 78.0%**. The scale is documented nowhere I could find. This silently produces a wrong number that looks plausible. | `data/registry/schema.json:682`; `data/docs/schema.md:330-340`; my `gate3.py` |
| 11 | MINOR | No checked-in expected router output exists | Task step 8 asked me to verify a trained router against a checked-in expected output. There is none — no `*expected*`/`*golden*` file, and `tests/` asserts no router metrics. I verified instead against the **released** predictions, which reproduce all 6 rows exactly (see Confirmed #6). Worth adding a tiny frozen expectation so the router path is regression-tested. | `find … -name "*expected*"` → empty |
| 12 | MINOR | README's "Every command above is exercised in CI" is not accurate | CI runs `pip install`, an import check, `pytest -q`, and `make smoke`. It does not run `make data`, `make reproduce-tables` or `make reproduce-figures` — the three commands in the block that sentence follows. (Two of them do not exist.) | `README.md:95`; `.github/workflows/tests.yml:24-49` |
| 13 | NOTE | One internal hostname appears in provenance docs | an internal facility inference endpoint URL appears once, in a provenance file documenting the serving endpoint. Flagged for a deliberate keep/remove decision, not as a defect. **Resolved after the audit:** the URL was replaced with a description of the interface, since it is unreachable outside the facility and a reader needs the interface, not the address. | `docs/provenance/models_and_versions.md:225` |
| 14 | NOTE | My own first mobile measurement was wrong — retracted | My initial 390px screenshot appeared to show severe clipping. A control page proved the instrument was lying: headless Chrome floors its window at ~500px, so `--window-size=390` actually rendered at 500. Re-measured inside a true 390px iframe, with a deliberately-overflowing positive control to prove the probe can fail: the page is **clean** (`scrollW=390 == clientW=390`). Recording this because a reader of an audit should know which findings were instrument artifacts. | control: `CTRL scrollW=500 clientW=500` at `--window-size=390`; positive control `CTRLBAD scrollW=900 clientW=390 OVER:DIV@900`; real page `IFRAME390 scrollW=390 clientW=390` |
| 15 | NOTE | The leakage *guard* is weak but the released *data* is genuinely clean | Distinct from Finding 8, and the more important of the two. I checked all 8 input files by column name **and** by value: no input column reconstructs `baseline/single/per/broadcast_correct`, `any_protocol_solved` (\|r\|>0.95 test) or matches `oracle_label`. No free-text field ≥120 chars exists anywhere in the released CSVs, and `probe_inputs.jsonl` carries identifiers only. No upstream problem text or gold answers are redistributed. | my `leak_data.py`: zero hits on both passes |

---

## What I verified as CORRECT (stated plainly)

1. **Clone integrity.** Branch `public-release`, SHA `05a697919a34148adec36af60652ba2f27a7b1f9`, working tree clean, 3 commits, 121 files.
2. **Environment.** Python **3.13.0** in a fresh venv. `make setup` installed cleanly (numpy 2.5.3, pandas 3.0.6, scikit-learn 1.9.1, matplotlib 3.11.2, pytest 9.1.1).
3. **Dataset validator.** Run unpiped per the dataset README: `python validate.py` → **exit code 0**, `RESULT: PASSED`. It self-reports row counts, coverage, oracle recomputation, split disjointness, leakage, checksums (44/44 match), and honestly lists 4 absent-by-design artifacts.
4. **Every data claim, verified by me and not from the docs:**
   - 15,088 rows total; 10 settings at exactly 4181/4181/1542/1542/741/741/565/565/515/515.
   - `(setting_id, problem_id)` unique on all 15,088; no duplicate rows under different ids.
   - Four protocol columns: zero nulls, strictly {0,1}.
   - **Oracle recomputed in the fixed order on every row: 0 mismatches of 15,088.** `oracle_label=='none'` iff `any_protocol_solved==0`: 0 violations. Vocabulary exactly the 5 documented labels.
   - Primary split: 3342/416/423 = 79.93/9.95/10.12, seed 42 stratified, **test n=423** as claimed, all three pairwise disjoint.
   - Six-setting split: 9046/1938/1944 = 69.97/14.99/15.04, seed 20260712, disjoint within every setting.
5. **Table reproduction.** With my adapter, `make reproduce-tables … REFERENCE_DIR=results/aggregate` → **exit 0**, `RESULT: PASS (every row matches the camera-ready tables exactly)` — 10/10 coverage rows and 10/10 oracle-distribution rows.
6. **Figure reproduction.** `make reproduce-figures` → exit 0, 2 PNGs; I rendered and read `fig_protocol_coverage.png` and its bars agree with the table.
7. **Headline, re-derived independently.** Joined post-answer predictions to labels on the **documented** key `example_id`: 4,181 joined → **4,151 parse_ok** → **failure AUROC 0.8847** (exact to 4dp). My own 2,000-resample bootstrap: [0.8735, 0.8951] vs published [0.8732, 0.8955] — inside the documented fourth-decimal tolerance. The repo's own `analyze_confidence.py` independently returns 0.8847 and [0.8735,0.8951].
8. **The join key was documented, and the trap is real.** `data/docs/schema.md:315-322` explicitly says "Join on `example_id`, never on `problem_uid_run`", explains why, and ships a crosswalk. I confirmed the trap empirically: joining on `problem_uid_run` yields **0 rows for all three Gemma settings** while the gpt-oss settings join perfectly — it would silently halve the data and look like it worked. I did **not** have to discover this myself; the docs got there first and were right.
9. **Router.** Trained per the quickstart (exit 0). All 6 released router rows reproduce exactly (n, router_solve, baseline_solve, oracle_solve). The three routers share **identical test ids** in every setting, and those ids equal the declared six-setting test split exactly.
10. **PER-vs-Broadcast interaction (PR-06).** Fully recomputed from matched labels alone: all 6 settings match on n, per%, bc%, and all four cell counts.
11. **Camera-ready rescoring.** gpt-oss OmniMath baseline = **2,376/4,181 = 56.8285% → 56.83%**. The May-era 2,373/56.76% is **not** present. No stale result silently replaces the camera-ready one.
12. **Security/privacy.** Scanned the clone and **all 3 commits of history**. No API keys, AWS/GitHub/HF tokens, private key blocks, passwords, `.env` files (only `.env.example`, correctly empty), scheduler job ids, or PBS artifacts. The only `/Users/`, `/lus/`, `/eagle/`, `/grand/` hits in history are the **detector's own regexes** in `tests/test_no_private_paths.py`. The dataset tree is clean of all of these. `bellayang@anl.gov` appears as the intended public contact.
13. **Website.** Served locally; all 14 local assets return 200. Exact paper title correct; **all 7 authors** present with correct affiliations; **"EMNLP 2026 ACCEPTED PAPER" visible in the first viewport** at 1440px along with all 5 buttons (verified by screenshot). All 4 images load and carry genuinely descriptive alt text. All 13 internal anchors resolve to defined ids. No horizontal overflow at **1440px or 390px** (measured, with a positive control). The elements extending past 390px are inside `.nav-links`, which sets `overflow-x: auto` deliberately.
14. **Expected-to-fail links behaved as expected.** Both Hugging Face repos → **401** (private during staging) and the GitHub Pages URL → **404** (not deployed). Reported as EXPECTED, not defects. arXiv 2608.14927 → 200.
15. **Cross-links.** README → arXiv, HF dataset, HF model, project page, GitHub. Dataset card → arXiv, HF model, GitHub, project page. Site → arXiv (4), HF dataset (3), HF model (3), GitHub (10). The only gap is that the dataset card does not link to **itself**, which is reasonable.
16. **Scope integrity.** MaScQA: **zero rows** anywhere in released data; it appears only as documented exclusion metadata (`benchmarks.csv`: `not released`, `CC-BY-NC-SA-4.0`, `excluded_entirely_no_matched_gemma_run_and_noncommercial_license`, `0` rows) — correct and expected. The six-vs-ten distinction is stated prominently in the README ("Important scope note"), `docs/limitations.md`, and the dataset card; nothing claims the deeper analyses cover ten. **Nothing claims "fully reproducible" or bit-for-bit** — the opposite is stated explicitly in four places.
17. **Bootstrap framing is honest.** Documented as 2,000 problem-level percentile resamples that "quantify uncertainty from *which problems* are in the benchmark, not from re-running a stochastic system," with one realized execution per problem-protocol pair stated as a limitation.
18. **"None" is correctly framed** as "Not a protocol — all four observed executions failed", a retrospective oracle action, not a fifth execution.
19. **Post-review provenance (all 8 rows).** Every row's stated public destination exists in the release. PR-01 (matched coverage), PR-04 (value targets), PR-05 (router), PR-06 (interaction) I re-derived myself from released per-problem data. PR-07 is explicitly `n/a — a definitional commitment, not a measurement` and is honestly labelled. See the caveat below for PR-02/03.
20. **`TODO.md` is unusually candid** — it documents that the post-answer probe cannot be re-run (Baseline final answers absent for all three gpt-oss settings, 0%), the 3-row scoring disagreement, the 73% clean-parse rate, and a rejected cost source that would have silently contradicted the paper's cost axis by 5.33x. This is the right way to ship a limitation.

---

## What I could NOT verify, and why

1. **The published AUPRC values (Finding 4).** I could not find any estimator that reproduces them from the released predictions. I tried `average_precision_score` (the repo's own function), the trapezoidal PR integral, and checked whether ties explain it (only 30 distinct confidence values). Across 6 settings the residual changes sign, which rules out a single convention difference. Either an input differs from what is released, or the column was computed by code not in this artifact.

2. **The post-answer probe cannot be re-run — by design, and honestly disclosed.** Baseline final-answer text is absent for all three gpt-oss settings (0/4,181, 0/1,542, 0/741). I verified the probe's *outputs* and *metrics*, not its *execution*. The release states this plainly in `TODO.md` and `docs/schema.md`; I am recording it as a scope boundary, not a defect.

3. **PR-02 and PR-03 per-problem sources are off-release.** Both cite Aurora HPC paths (`<hpc-run-2026-07-13>/results/full_p0_addon/.../predictions.jsonl`). By my isolation rules I could not and did not look at them. What I *can* say: the released `postanswer_confidence_predictions.csv` reproduces the headline AUROC, parse rate and positive counts exactly, so the claims those rows support are independently confirmed from released data even though their cited raw source is not in the release. A reader cannot audit the cited path itself.

4. **Upstream problem text and gold answers.** Not released (deliberately, for licensing). I verified their *absence* rather than their correctness, so I cannot check whether the recorded outcomes are correct against the true gold answers — only that they are internally consistent.

5. **Protocol execution (Stage 1 / Track C).** Requires a live model endpoint. Out of scope for an offline audit; the repo is clear that it does not reproduce offline.

6. **The paper PDF's own numbers.** I checked the released artifacts against the checked-in camera-ready aggregate CSVs, not against the PDF text.

7. **Whether the four protocol configs are *semantically* right.** Finding 1 shows the test and the configs disagree on schema. I verified the disagreement, not which side is correct — that needs the release lead.

---

## Recommended fix order

1. Reconcile `tests/test_schema.py` with the four protocol configs (Finding 1) — this is what a newcomer hits first, and it turns the CI badge red.
2. Ship a documented adapter or teach `load_matched_dir` to read the released combined `matched_labels.csv` schema (Finding 2), then re-test the documented command verbatim.
3. Add `make data` and `make validate-data`, or remove them from the docs (Finding 3).
4. Resolve the AUPRC column (Finding 4) — recompute from released data, or state which code produced it.
5. Fix `make setup` to create a venv, or correct the sentence (Finding 5).
6. Add `docs/data_schema.md` or repoint the link (Finding 6).
7. Correct the artifact matrix's generating commands and expected outputs (Finding 7).
8. Add `^.*_success$` / `^.*_failed$` to the leakage patterns (Finding 8).
9. Fix the fallback-row sentence and document the 0–100 scale (Findings 9, 10).

---

## Audit hygiene note

**The staging tree changed during this audit, by another party.** I copied it at
19:37; at 20:01 and 20:09 two files were modified upstream. I re-diffed my copy
against the live tree at the end:

- **Every `data/`, `registry/`, and `docs/` file is byte-identical.** No released
  data changed.
- Only `validate.py` and its checksum line differ. The change hardens the
  checksum-coverage check to ignore tool-created infrastructure
  (`.cache/`, `.git/`, `__pycache__`, `.DS_Store`, `.gitattributes`) — a
  download-artifact false-positive fix, not a data or logic change.
- I re-ran the **new** validator against a fresh copy: **exit 0, RESULT: PASSED.**

Every finding above therefore still holds against the current staging tree.
Recording this because an audit that silently used a superseded snapshot would be
unfalsifiable by a reader.

**Isolation confirmed.** I wrote only under `/tmp/audit_e/`. The source repo is
`git status` clean and the staging tree carries no files I created (no `__pycache__`,
no `.pyc`). I read none of the excluded paths.

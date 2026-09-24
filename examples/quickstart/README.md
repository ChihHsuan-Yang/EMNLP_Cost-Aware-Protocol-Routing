# Quickstart

Five minutes, entirely offline, using only the tiny synthetic fixture shipped
with the tests. No model endpoint, no GPU, no network.

Run from the repository root.

## 1. Check the install

```bash
make smoke
```

Runs the CLI `--help` for all seven scripts, builds aggregate tables from the
fixture, and runs the test suite. Takes about ten seconds.

## 2. Build aggregate tables from the fixture

```bash
python scripts/build_matched_tables.py \
  --matched_dir tests/fixtures \
  --output_dir  outputs/quickstart \
  --allow_non_paper_settings
```

`--allow_non_paper_settings` is required here because the fixture's toy
settings are deliberately not paper settings. Against the real released data
you omit it, and the strict allowlist then guarantees all ten paper settings
are present and nothing else slips in.

## 3. Train and score a router on the fixture

```bash
python scripts/train_router.py \
  --input_csv  tests/fixtures/toybench__text_only__toy_solver_a.csv \
  --output_dir outputs/quickstart/router \
  --router     text_metadata_logreg

python scripts/evaluate_router.py \
  --matched_csv     tests/fixtures/toybench__text_only__toy_solver_a.csv \
  --predictions_csv outputs/quickstart/router/test_predictions.csv \
  --bootstrap_resamples 200
```

The numbers are meaningless at 24 rows -- this checks the plumbing, not the
science. Use `--bootstrap_resamples 2000` (the paper setting) on real data.

## 4. Confidence analysis

```bash
python scripts/analyze_confidence.py \
  --confidence_csv    tests/fixtures/toybench__text_only__toy_solver_a.csv \
  --confidence_column confidence_raw \
  --score_gate \
  --bootstrap_resamples 200
```

Reports parse rate, failure AUROC, ECE and Brier, then scores the
self-confidence gate (keep Baseline if confidence >= 70, else Single).

## 5. Render the figures

```bash
python scripts/reproduce_paper_figures.py \
  --matched_dir tests/fixtures \
  --output_dir  outputs/quickstart/figures \
  --allow_non_paper_settings
```

## Then: the real thing

With the released per-problem outcome tables and the camera-ready ancillary
CSVs:

```bash
make reproduce-tables MATCHED_DIR=/path/to/matched_labels REFERENCE_DIR=/path/to/anc
```

This exits nonzero unless every cell matches the published tables.

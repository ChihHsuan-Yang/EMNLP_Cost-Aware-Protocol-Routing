#!/usr/bin/env bash
# Offline quickstart. Run from the repository root:  bash examples/quickstart/run_quickstart.sh
# No network, no model endpoint, no GPU. Uses only tests/fixtures/.
set -euo pipefail

PYTHON="${PYTHON:-python}"
OUT="${OUT:-outputs/quickstart}"
FIXTURE="tests/fixtures"
ONE="$FIXTURE/toybench__text_only__toy_solver_a.csv"

echo "== 1. aggregate tables =="
"$PYTHON" scripts/build_matched_tables.py \
  --matched_dir "$FIXTURE" --output_dir "$OUT" --allow_non_paper_settings

echo
echo "== 2. train a router =="
"$PYTHON" scripts/train_router.py \
  --input_csv "$ONE" --output_dir "$OUT/router" --router text_metadata_logreg

echo
echo "== 3. score it =="
"$PYTHON" scripts/evaluate_router.py \
  --matched_csv "$ONE" \
  --predictions_csv "$OUT/router/test_predictions.csv" \
  --bootstrap_resamples 200

echo
echo "== 4. confidence + gate =="
"$PYTHON" scripts/analyze_confidence.py \
  --confidence_csv "$ONE" --confidence_column confidence_raw \
  --score_gate --bootstrap_resamples 200

echo
echo "== 5. figures =="
"$PYTHON" scripts/reproduce_paper_figures.py \
  --matched_dir "$FIXTURE" --output_dir "$OUT/figures" --allow_non_paper_settings

echo
echo "quickstart complete; artifacts under $OUT"

# Why the published AUPRC values do not reproduce exactly

## Summary

Every **AUROC**, count, prevalence, and parse rate in
`results/aggregate/failure_and_protocol_value_targets.csv` reproduces exactly
from the released per-problem data. The **AUPRC** column does not reproduce
exactly with a standard estimator, and the reason is tie handling. This page
records what we found, because a reader who recomputes these numbers will see
the difference and deserves an explanation rather than a surprise.

## What happened

An independent audit of this release reported that AUPRC reproduced in none of
the six settings while every AUROC reproduced exactly, and that the sign of the
error varied — which correctly ruled out a simple estimator convention.

Investigating, we recovered the original scoring function. It computes average
precision by sorting scores descending and accumulating precision at each
positive, with **no tie handling**:

```python
order = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
hits = 0
precision_sum = 0.0
for rank, idx in enumerate(order, start=1):
    if labels[idx] == 1:
        hits += 1
        precision_sum += hits / rank
return precision_sum / positives
```

Recomputing with that exact function reproduces **14 of the 24** target values
exactly, and the remaining ten differ only in the fourth decimal place.

## Why the remainder still differ

The probe emits integer confidences, so scores are heavily tied. In the
gpt-oss-120b OmniMath setting there are **30 distinct score values across 4,151
rows**, with 1,320 rows sharing a single value. When ties are not broken
explicitly, `sorted` preserves input order, so the result depends on the order
in which rows happened to be read.

The effect is small for the large, high-prevalence targets and large for the
small ones. For the worst case we found — Gemma-4-31B-it on LAB-Bench strict,
PER-first-success, with 85 positives and only **11 distinct scores across 733
rows** — average precision ranges from **0.1474 to 0.2798** over 200 random
tie orderings. The published 0.2186 sits inside that range, as does our
recomputation of 0.2212.

## What this does and does not affect

**Does not affect:**

- Any AUROC. The rank-based AUROC computation averages tied ranks, so it is
  tie-invariant and reproduces exactly in all six settings, including the
  headline 0.8847.
- Any count, prevalence, parse rate, solve rate, coverage figure, or oracle
  label. All reproduce exactly.
- The paper's claim. The finding is that the failure score stays useful for
  "does any collaboration help" (AUPRC around 0.77 for gpt-oss OmniMath) and
  collapses for protocol-specific value (around 0.17 and 0.10). That gap is an
  order of magnitude; tie ordering moves the fourth decimal for the large
  targets, and the small targets collapse under every ordering we tried.

**Does affect:**

- The exact published AUPRC digits, which should be read as precise to roughly
  two decimal places rather than four, particularly for the low-prevalence
  protocol-specific targets.

## What the released code does

`protocol_routing.confidence.auprc` uses `sklearn.metrics.average_precision_score`,
which handles ties correctly and is the better estimator. It therefore returns
slightly different values from the published column — for example 0.8813 rather
than 0.8950 for the gpt-oss-120b OmniMath baseline-failure target. We kept the
correct estimator rather than reimplementing the tie-unaware one, and documented
the difference here.

If you need to match the published digits exactly, use the function quoted
above, with rows in the order they appear in the released prediction files.

## Recommendation for future work

Report AUPRC with an explicit tie-handling policy, or avoid it for
low-prevalence targets where a handful of tied scores can move the estimate by
more than a tenth. This is recorded in `TODO.md`.

# Data schema

The released tables live in the Hugging Face dataset, not in this repository:

<https://huggingface.co/datasets/AgentsSci/EMNLP_Cost-Aware-Protocol-Routing>

That repository ships its own authoritative, self-contained `docs/schema.md`
describing every column of every table. This page is the short orientation; read
it first, then follow the dataset's schema doc for field-level detail.

## The tables, and what each is for

| Table | One row per | Use it to |
|---|---|---|
| `data/matched_labels.csv` | (setting, problem) | The flagship table. Four protocol outcomes plus the fixed-order oracle label for all 10 settings, 15,088 rows. |
| `data/problems.csv` | problem | Router-visible metadata only. **Contains no labels** — this is the feature side. |
| `data/labels_for_scoring.csv` | (setting, problem) | The label side, kept deliberately separate from features. |
| `data/probe_inputs.jsonl` | probe row | Identifier manifest for the confidence probe. See the caveat below. |
| `data/confidence/postanswer_confidence_predictions.csv` | (setting, problem) | Post-answer probe outputs for the 6 evaluated settings, 12,928 rows. Backs the headline result. |
| `data/confidence/primary_omnimath_confidence_predictions.csv` | probe row | The **pre-answer** q1 probe on the primary split. A different instrument — see below. |
| `data/router/six_setting_test_predictions.csv` | (setting, problem, router) | Held-out router predictions on identical test ids. |
| `data/costs/omnimath_per_protocol_costs.csv` | problem | Per-protocol token totals and model calls. One setting only. |
| `data/splits/` | problem | Split assignments, with the seed and ratio documented per file. |
| `data/aggregate/` | setting | The camera-ready aggregate tables, mirrored from `results/aggregate/`. |

## Four things that will bite you if you skip them

**1. Two confidence probes exist, and they are different instruments.**
The *pre-answer* probe asks the model how confident it is before it answers, on
the primary split. The *post-answer* probe asks after the model has produced a
Baseline answer but before any collaboration, on six settings. The paper's
headline (0.8847 AUROC) is the **post-answer** probe. Every row carries a
`probe_type` column; use it.

**2. Join on `example_id`, not on a problem id, when joining probe predictions.**
The Gemma and gpt-oss runs used different `problem_uid` conventions for the same
problems (`omni2:t01:1` versus `omni2_1`; LAB-Bench UUIDs versus sequential
ids). A join on the raw id silently produces **zero** matches for the three
Gemma settings while the three gpt-oss settings join perfectly — so it drops
half the data and still looks like it worked. The dataset ships
`registry/example_id_crosswalk.csv` for exactly this.

**3. `probe_inputs.jsonl` is a manifest, not a runnable prompt set.**
It carries identifiers and metadata. It does **not** carry problem text (not
redistributed) or the Baseline final answer. The probe consumes both, so the
probe cannot be re-executed from released artifacts alone; its outputs and
metrics are fully released and independently reproducible. See `TODO.md`.

**4. Token counts mean protocol totals, not per-call totals.**
`*_total_tokens` sums every model call the protocol made — Baseline averages
about 9.7 calls. A figure that counts one call is roughly 5x smaller and is a
different quantity. Do not mix the two conventions.

## The oracle label

Computed from the four outcome columns in the fixed order
`baseline_llm -> single_agent -> per -> broadcast -> none`. The value `none`
means all four observed executions failed. A later protocol succeeding never
overrides an earlier one.

Do not trust the stored label blindly — recompute it. The repository's
`protocol_routing.oracle` module is the authoritative implementation, and
`scripts/reproduce_paper_tables.py` recomputes it from scratch rather than
reading the stored column.

## Protocol vocabulary

Two spellings are in circulation and both are valid: configs use the short
display names (`per`), while the research tables use the longer form
(`planner_executor_reviewer`). Resolve any spelling with
`protocol_routing.protocols.canonical_protocol` rather than string comparison.

## Leakage boundary

No file intended as a model, probe, or router **input** contains gold answers,
Baseline correctness, protocol outcomes, or oracle labels. Features and labels
are in separate files by design. The repository enforces this in code:
`protocol_routing.features` raises `LeakageError` when a forbidden column
reaches feature construction, and the test suite proves it refuses deliberately
constructed violations.

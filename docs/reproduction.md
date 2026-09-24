# Reproduction guide

This page separates what you can reproduce on a laptop from what needs model
endpoints and a compute allocation. Read the split before you start.

## Two very different kinds of "reproduce"

**A. Offline analyses (this is most of the paper, and it runs anywhere).**
Starting from the released per-problem outcomes, you can regenerate the matched
coverage table, the oracle label distribution, the held-out router evaluations,
the post-answer confidence metrics, and the PER-versus-Broadcast interaction
analysis. No GPU. No API key. No allocation. Minutes, not days.

**B. Protocol execution (needs a model endpoint and real compute).**
Producing the outcomes in the first place means running all four protocols over
every problem against `openai/gpt-oss-120b` and `google/gemma-4-31B-it`. This
repository ships the runner, the protocol configs, the evaluator, and a
deterministic **mock backend** so you can exercise the complete four-protocol
pipeline end to end with no network and no cost. Pointing it at a real
OpenAI-compatible endpoint reruns the experiments for real. See
[REPRODUCE.md](REPRODUCE.md) for requirements and expected cost.

Three kinds of "reproduce" are **not** the same thing, and we keep them apart:

1. **Exact reproduction from released outcomes** - deterministic arithmetic over
   the published per-problem data. This is what Track A does, and it matches the
   camera-ready tables to the last published digit.
2. **Functional rerun with compatible public models** - Track B against a live
   endpoint. Expect broadly similar findings, not identical numbers.
3. **Exact historical execution** - **not possible.** The original serving
   environment no longer exists and no model snapshot was version-pinned at run
   time. We do not claim bit-for-bit reproducibility and neither should anyone
   citing this artifact.

If a command in this repository is in group B, it says so.

## What the offline path can check

Each of these is a claim in the paper that you can verify yourself against the
camera-ready aggregate tables shipped in `results/aggregate/`:

| Check | Camera-ready file |
|---|---|
| Four-protocol solve rates and oracle coverage, 10 settings | `matched_protocol_coverage.csv` |
| Fixed-order oracle label distribution, 10 settings | `oracle_label_distribution.csv` |
| Post-answer confidence metrics, 6 settings | `postanswer_confidence.csv` |
| Failure-risk versus collaboration-value targets | `failure_and_protocol_value_targets.csv` |
| Held-out router evaluation, 6 settings | `heldout_router_evaluation.csv` |
| Paired router differences | `heldout_router_paired_differences.csv` |
| PER versus Broadcast interaction | `per_broadcast_interaction.csv` |
| Representative policies on the primary split | `main_routing_heldout.csv` |

## Numerical tolerance

Solve rates, coverage percentages, and oracle label distributions are exact
arithmetic over integer counts: they should match to the last published digit,
and the reproduction script treats any deviation as a failure.

Bootstrap confidence intervals are **not** expected to match exactly. They are
2,000-resample problem-level percentile intervals, and a different resampling
seed moves the endpoints in the fourth decimal place. For example, reproducing
the headline gpt-oss-120b OmniMath failure AUROC yields the published point
estimate 0.8847 exactly, while an independently seeded 2,000-resample interval
gives [0.8733, 0.8956] against the published [0.8732, 0.8955]. Point estimates
are checked strictly; interval endpoints are checked with a documented tolerance.

## The two OmniMath scoring passes

You may encounter an earlier scoring pass of the OmniMath gpt-oss-120b setting
that reports 2,373 Baseline successes instead of 2,376 (56.76% versus the
published 56.83%). The two passes describe the *same* protocol executions and
differ on exactly 3 of 4,181 problems, all Baseline re-scored from incorrect to
correct; PER and Broadcast outcomes are identical across all 4,181. The
camera-ready labels shipped here are authoritative and are what reproduces the
published tables. See `docs/provenance/` for the problem-level detail.

## Getting the data

The per-problem outcomes live in the Hugging Face dataset, not in this Git
repository, because they are too large to belong in Git:

<https://huggingface.co/datasets/AgentsSci/EMNLP_Cost-Aware-Protocol-Routing>

A small fixture is committed under `tests/fixtures/` so the test suite and the
smoke workflow run with no download at all.

## Exact commands

See the repository `README.md` for the tested, copy-pasteable command sequence
(`make setup`, `make test`, `make smoke`, `make reproduce-tables`,
`make reproduce-figures`). Every command documented there has been executed
against this tree; commands are not documented from memory.

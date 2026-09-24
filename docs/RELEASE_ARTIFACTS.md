# Release artifacts

Every public artifact for the EMNLP 2026 paper *LLMs Can Predict Failure Risk,
But Struggle to Predict Which Collaboration Protocol Pays Off: Cost-Aware
Protocol Routing Across Reasoning Tasks*, with the revision each was verified at.

**All URLs below returned HTTP 200 when this file was last updated
(2026-09-24).** The link checker re-runs them on every push and weekly; see
`.github/workflows/link-check.yml`.

## Public URLs

| Artifact | URL |
|---|---|
| Paper (arXiv abstract) — **cite this** | <https://arxiv.org/abs/2608.14927> |
| Paper (PDF) | <https://arxiv.org/pdf/2608.14927> |
| Code repository | <https://github.com/ChihHsuan-Yang/EMNLP_Cost-Aware-Protocol-Routing> |
| Project website | <https://chihhsuan-yang.github.io/EMNLP_Cost-Aware-Protocol-Routing/> |
| Dataset card | <https://huggingface.co/datasets/AgentsSci/EMNLP_Cost-Aware-Protocol-Routing> |
| Model card (trained router) | <https://huggingface.co/AgentsSci/EMNLP_Cost-Aware-Protocol-Routing> |
| Hugging Face collection | <https://huggingface.co/collections/AgentsSci/cost-aware-protocol-routing-emnlp-2026-6ab4a6858f76a3ef1ffc18e6> |
| Release tag | <https://github.com/ChihHsuan-Yang/EMNLP_Cost-Aware-Protocol-Routing/releases/tag/v1.0.0> |

## Pinned revisions

Pin these if you need a result to stay reproducible. `main` moves; these do not.

| Artifact | Revision |
|---|---|
| Code, release `v1.0.0` | `0193afce215f953b5e03455e482a08f15e732fa1` |
| Hugging Face dataset | `00724cf1398418499cf3ee61af5f5e49a1f3f205` |
| Hugging Face model | `294c75175cb521ee76cb43ecfd66e704bcceda73` |
| arXiv | `arXiv:2608.14927` (submitted 2026-08-14) |

```bash
# Code at the tagged release
git clone --branch v1.0.0 \
  https://github.com/ChihHsuan-Yang/EMNLP_Cost-Aware-Protocol-Routing.git

# Data at a fixed revision
hf download AgentsSci/EMNLP_Cost-Aware-Protocol-Routing \
  --repo-type dataset \
  --revision 00724cf1398418499cf3ee61af5f5e49a1f3f205 \
  --local-dir data/emnlp_protocol_routing

# Trained router at a fixed revision
hf download AgentsSci/EMNLP_Cost-Aware-Protocol-Routing \
  --revision 294c75175cb521ee76cb43ecfd66e704bcceda73 \
  --local-dir models/protocol_router
```

## Upstream benchmarks

Problem text and gold answers are **not** redistributed here. Each benchmark
stays under its own licence; see [`NOTICE`](../NOTICE) and the dataset card's
reconstruction instructions.

| Benchmark | Upstream | Licence | Pinned |
|---|---|---|---|
| Omni-MATH 2 | <https://huggingface.co/datasets/martheballon/Omni-MATH-2> | Apache-2.0 | not pinned |
| JEEBench | <https://huggingface.co/datasets/daman1209arora/jeebench> | MIT | not pinned |
| SciBench | <https://huggingface.co/datasets/xw27/scibench> | MIT (upstream `LICENSE`; the HF card declares none) | not pinned |
| LAB-Bench | <https://huggingface.co/datasets/futurehouse/lab-bench> | CC-BY-SA-4.0 | `5c77cec648430f30611808808861eb86f81d5eaa` |

## What is at each destination

- **Repository** — analysis package, protocol execution code with an offline
  mock backend, the eight camera-ready aggregate tables, provenance records, the
  independent audit report, and the website source.
- **Dataset** — matched four-protocol outcomes for all 10 settings (15,088
  rows), post-answer confidence predictions for 6 settings (12,928 rows),
  held-out router predictions, splits, per-protocol token costs for one setting,
  and a stdlib-only `validate.py`.
- **Model** — the trained metadata-only router: estimator, fitted feature
  builders, a verified label map, held-out predictions, and a runnable example.

## Contact

Chih-Hsuan (Bella) Yang — <bellayang@anl.gov>

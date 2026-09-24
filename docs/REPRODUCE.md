# Reproducing this paper

Written for a researcher who has never seen this project. No knowledge of our
internal repositories, cluster, or naming conventions is assumed. If any step
here depends on something you do not have, that is a bug — please open an issue.

---

## 1. What this project studies

Running a language model with more collaboration solves more problems but costs
more tokens. This paper asks whether you can tell **in advance**, for a given
problem, whether the extra collaboration is worth paying for and *which kind* to
use. Every problem was run under four protocols with the solver held fixed, so
the protocols can be compared on matched problems.

The finding: a model's own confidence predicts **whether its first answer will
fail** well (0.8847 AUROC), and predicts **which protocol will pay off** poorly
(0.1674 and 0.1041 AUPRC for PER- and Broadcast-specific value).

New to the terminology? Read [protocol_definitions.md](protocol_definitions.md)
first — it defines Baseline, Single, PER, Broadcast, the fixed-order oracle, the
self-confidence gate, and Tier-majority.

---

## 2. Three entry points

Pick the one that matches what you want. They are ordered by cost.

| | What it does | Needs | Time |
|---|---|---|---|
| **A. Smoke test** | Exercises the whole pipeline on a tiny committed fixture | Nothing but Python | ~5 min |
| **B. Offline paper reproduction** | Regenerates the paper's principal tables and figures from released outcomes | A data download (~tens of MB) | ~15 min |
| **C. Full protocol rerun** | Reruns Baseline/Single/PER/Broadcast for real | An OpenAI-compatible endpoint, real compute and budget | Hours to days |

**Most readers want A then B.** C is for people who want to extend the study.

---

## 3. System requirements

| | Track A + B | Track C |
|---|---|---|
| OS | macOS or Linux | macOS or Linux |
| Python | 3.9 or newer | 3.9 or newer |
| CPU | any modern laptop | any modern laptop for orchestration |
| GPU | **none** | none locally, unless you self-host the solver |
| Disk | ~1 GB | tens to hundreds of GB for traces |
| Network | for the data download only | sustained access to a model endpoint |
| Credentials | **none** | an API key for your chosen provider |

Track A needs no network at all after cloning.

---

## 4. Install

```bash
git clone https://github.com/ChihHsuan-Yang/EMNLP_Cost-Aware-Protocol-Routing.git
cd EMNLP_Cost-Aware-Protocol-Routing
make setup
```

`make setup` creates a virtual environment and installs the package. If you
prefer to manage environments yourself, any of these works:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"   # pip
uv venv && uv pip install -e ".[test]"                                          # uv
conda env create -f environment.yml && conda activate protocol-routing          # conda
```

On an HPC login node, load a Python module first and install into a user prefix
or a virtual environment on a filesystem you can write to. Nothing in Track A or
B needs a scheduler allocation.

---

## 5. Entry point A — the five-minute smoke test

```bash
make test    # schema, oracle order, leakage, and path tests
make smoke   # tiny end-to-end run on the committed fixture
```

This makes **no network calls and no model calls**. It uses only the small
fixture under `tests/fixtures/`. If this passes, your environment is good.

---

## 6. Entry point B — offline paper reproduction

### 6.1 Download the released data

```bash
hf download AgentsSci/EMNLP_Cost-Aware-Protocol-Routing \
  --repo-type dataset \
  --local-dir data/emnlp_protocol_routing
```

Python equivalent:

```python
from huggingface_hub import snapshot_download
snapshot_download(
    "AgentsSci/EMNLP_Cost-Aware-Protocol-Routing",
    repo_type="dataset",
    local_dir="data/emnlp_protocol_routing",
)
```

Install the CLI with `pip install -U huggingface_hub` if `hf` is not found.
(The older `huggingface-cli` entry point is deprecated; use `hf`.)

### 6.2 Validate what you downloaded

```bash
make validate-data
```

This prints the release version, schema version, expected files, row counts,
benchmark/model/protocol coverage, checksum status, and any missing optional
artifact. Read its output before trusting anything downstream.

### 6.3 Reproduce the tables and figures

```bash
make reproduce-tables \
  MATCHED_DIR=data/emnlp_protocol_routing/data/matched_labels.csv \
  REFERENCE_DIR=results/aggregate

make reproduce-figures \
  MATCHED_DIR=data/emnlp_protocol_routing/data/matched_labels.csv
```

`MATCHED_DIR` accepts either the single combined `matched_labels.csv` you just
downloaded, or a directory of per-setting CSVs. The released dataset ships the
combined form, so the command above is the one most readers want.

`make reproduce-tables` **fails loudly** on any mismatch rather than reporting
success. See [reproduction.md](reproduction.md) for the numerical tolerances —
in short, solve rates and counts must match exactly, while bootstrap interval
endpoints are allowed to move in the fourth decimal because they depend on the
resampling seed.

### 6.4 Train and evaluate the lightweight routers

```bash
python scripts/train_router.py --help
python scripts/evaluate_router.py --help
```

The routers are small scikit-learn models over text and metadata features. They
train in minutes on CPU. Their features never include gold answers, correctness,
protocol outcomes, or oracle labels — `tests/test_no_leakage.py` enforces that.

---

## 7. Entry point C — full protocol rerun

**Be honest with yourself about cost before starting.** This reruns four
protocols over up to 4,181 problems per setting against a large model.

### 7.1 Try it with no endpoint first

A deterministic mock backend ships with the repository so you can exercise the
complete four-protocol pipeline offline, for free, before spending anything:

```bash
python -m protocol_routing_exec.run_protocol \
  --dataset-config configs/datasets/omnimath.yaml \
  --model-config configs/models/gpt_oss_120b.yaml \
  --protocol-config configs/protocols/baseline.yaml \
  --provider-config configs/providers/mock.yaml \
  --limit 5 \
  --output-dir outputs/mock_demo
```

### 7.2 Configure a real provider

Copy `.env.example` to `.env` and set your own values:

```bash
INFERENCE_BASE_URL=https://provider.example/v1
INFERENCE_API_KEY=...        # never commit this
DATA_ROOT=./data
OUTPUT_ROOT=./outputs
```

Any OpenAI-compatible endpoint works — a hosted provider, or a local server such
as vLLM, SGLang, or llama.cpp's server. Point `INFERENCE_BASE_URL` at it. Nothing
in this repository is tied to our cluster.

### 7.3 Obtain the benchmarks

We do not redistribute problem text. `configs/datasets/*.yaml` names each
upstream source, its pinned revision where known, and the filtering applied.
See [`NOTICE`](../NOTICE) for licenses.

### 7.4 Run, score, and analyze

Run each protocol, then build matched outcomes, oracle labels, splits, routers,
and analyses with the same Track B commands. Every run directory records its
resolved config, manifest, environment, token counts, evaluation results, log,
and checksums — so a run can be audited later.

---

## 8. What is and is not reproducible

Three different claims, often conflated:

1. **Exact reproduction from released outcomes.** Deterministic arithmetic over
   the published per-problem data. Matches the camera-ready tables to the last
   published digit. **This is Track B, and it is the strong claim.**
2. **Functional rerun with compatible public models.** Track C against a live
   endpoint. Expect broadly similar findings, **not identical numbers**.
3. **Exact historical execution.** **Not possible.** The original serving
   environment no longer exists, and no model snapshot was version-pinned at run
   time. We do not claim bit-for-bit reproducibility, and nothing in this
   artifact should be cited as though we did.

---

## 9. Expected outputs and tolerances

See [reproduction/paper_artifact_matrix.md](reproduction/paper_artifact_matrix.md)
for a row per paper table and figure: its input data, generating command,
expected output file, expected metric, tolerance, and verification status.

---

## 10. Troubleshooting

**`hf: command not found`** — `pip install -U huggingface_hub`.

**`make: command not found`** (some minimal Linux images) — open the `Makefile`
and run the underlying commands directly; they are plain shell one-liners.

**A checksum fails after download** — re-run the download; a partial transfer is
far more likely than a corrupted release. If it persists, open an issue with the
output of `make validate-data`.

**`reproduce-tables` reports a mismatch** — that is the test doing its job.
Please open an issue with the diff rather than adjusting a tolerance.

**A number differs in the fourth decimal** — expected for bootstrap intervals
(see §6.3). Point estimates should be exact; if one is not, that is a real bug.

**Rate limiting during Track C** — lower the worker count in your provider
config. The runner retries with backoff, but it cannot fix an exhausted quota.

---

## 11. Getting help

Open an issue at
<https://github.com/ChihHsuan-Yang/EMNLP_Cost-Aware-Protocol-Routing/issues>,
or email bellayang@anl.gov.

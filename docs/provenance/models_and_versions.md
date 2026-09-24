# Model Identifiers and Versions

Agent A, 2026-09-23. Every identifier below is quoted from a file read in this
session, with the path and line. Nothing here is recalled or inferred from
naming convention.

---

## Summary

| Role | Public identifier | Evidence strength | Provider snapshot / revision |
| --- | --- | --- | --- |
| Solver family A | `openai/gpt-oss-120b` | **VERIFIED**, 4 independent sources | **UNRESOLVED** |
| Solver family B | `google/gemma-4-31B-it` | **VERIFIED**, 4 independent sources | **UNRESOLVED** |
| Reduced actor-stack check | `google/gemma-3-27b-it` | **VERIFIED**, run manifest | **UNRESOLVED** |
| Evaluator / judge | `openai/gpt-oss-120b` | **VERIFIED**, run configs + outcome records | **UNRESOLVED** |
| Serving endpoint | ALCF Sophia vLLM, OpenAI-compatible | **VERIFIED** | n/a |

**The paper's own usage is `google/gemma-4-31B-it`** — note the capital `B` in
`31B` and lowercase `it`. Do not normalize it to `gemma-4-31b-it`; the project
explicitly standardized on this spelling (see §2 below).

---

## 1. `openai/gpt-oss-120b`

### Evidence

`<camera-ready>/results/additional_analysis/aggregate_solve_oracle_coverage.csv`,
`model_endpoint` column, line 3:

```
jeebench__text_only__gpt_oss_120b,gpt_oss_120b,openai/gpt-oss-120b,science,jeebench,text_only,gpt_oss_120b,515,41.55,…
```

Same string in the `model` column of
`.../results/additional_analysis/confidence_probe_metrics.csv`, line 3:

```
gpt-oss-120b OmniMath,omnimath2__competition_math_4181__gpt_oss_120b,openai/gpt-oss-120b,math,4181,0.9928,0.8847,…
```

`<post-review-extract>/results_2026-07-12/manifests/no_model_manifest.json`,
`available_settings[].model_endpoint` — the string `"openai/gpt-oss-120b"`
appears for all 6 gpt-oss settings.

`<post-review-extract>/results_2026-07-12/metrics/final_metrics_p0.csv`,
line 3, `model` column:

```
labbench__llm_strict__gpt_oss_120b,openai/gpt-oss-120b,biology,741,0.9703,0.5814,…
```

`<experiment-repo>/code/confident_routing/configs/baseline_llm/config.yaml`,
line 90 (solver agent) and line 107 (evaluator agent):

```yaml
    llm:
      llm_type: gpt-3.5-turbo
      model: openai/gpt-oss-120b
      temperature: 0
      max_tokens: 4096
```

(The `llm_type: gpt-3.5-turbo` line is an AgentVerse framework adapter selector,
not a model. The `model:` field is the served model. This is worth stating in
the release README so a reader does not mistake it for a GPT-3.5 run.)

Paper usage, `sections/appendix_additional_analyses.tex` line 49:

```latex
condition. Both \texttt{openai/gpt-oss-120b} \citep{openai_gptoss_model} and
```

Citation target, `custom.bib`:

```bibtex
@misc{openai_gptoss_model,
  author = {{OpenAI}},
  title = {{gpt-oss-120b} \& {gpt-oss-20b} {Model Card}},
  year = {2025}, month = aug,
  url = {https://openai.com/index/gpt-oss-model-card/},
  note = {Accessed August 24, 2026}
}
```

### Snapshot / revision: UNRESOLVED

No run manifest, config, PBS job, or outcome record on disk carries a model
revision, weights hash, commit, quantization setting, or serving-version field
for gpt-oss-120b. I searched `no_model_manifest.json`, the run2 router
`manifest.json`, all `jobs/*.pbs` and `jobs/*.sh`, the `confident_routing`
configs, and the `outcomes.jsonl` schema. The outcome records carry
`actor_set_id: "gpt-oss-120b"` and `evaluator_id: "gpt-oss-120b"` — the bare
name only, with no version.

State this as UNRESOLVED in the release. Do **not** substitute an OpenAI release
date or a HuggingFace revision that was not recorded at run time. The honest
statement is: served via the ALCF Sophia vLLM endpoint over the run window
(May–July 2026); the serving-side model revision was not logged.

---

## 2. `google/gemma-4-31B-it`

### Evidence

`.../results/additional_analysis/aggregate_solve_oracle_coverage.csv`,
`model_endpoint`, line 2:

```
jeebench__text_only__gemma_4_31b,gemma_4_31b,google/gemma-4-31B-it,science,jeebench,text_only,gemma_4_31b,515,70.49,…
```

`.../results/additional_analysis/confidence_probe_metrics.csv`, line 2:

```
Gemma-4-31B-it OmniMath,omnimath2__competition_math_4181__gemma_4_31b,google/gemma-4-31B-it,math,4181,0.9993,0.8012,…
```

`no_model_manifest.json` — `"model_endpoint": "google/gemma-4-31B-it"` for all
6 gemma_4_31b settings.

`.../rebuttal/results_2026-07-12/metrics/final_metrics_p0.csv`, line 2:

```
labbench__llm_strict__gemma_4_31b,google/gemma-4-31B-it,biology,741,0.9892,0.8637,…
```

`matched_labels/omnimath2__competition_math_4181__gemma_4_31b.csv`, row 1,
`model_endpoint` column: `google/gemma-4-31B-it`.

Paper usage, `sections/appendix_additional_analyses.tex` line 50:

```latex
\texttt{google/gemma-4-31B-it} \citep{gemma4report} cover all five evaluation
```

### The spelling was a deliberate project decision

`<post-review-extract>/exact_paper_context_verification_2026-07-13.md`,
line 154:

> Use `Gemma-4-31B` or endpoint `google/gemma-4-31B-it`; avoid bare `Gemma-4` unless the table caption defines it as shorthand.

Repeated at `post_verification_revision_and_aurora_plan_2026-07-13.md` line 78:

> Use `Gemma-4-31B` or `google/gemma-4-31B-it`, not bare `Gemma-4`, unless table shorthand is explicitly defined.

Display name in the paper's tables is `Gemma-4-31B-it`. Keep both spellings as
they are.

### Snapshot / revision: UNRESOLVED

Same finding as gpt-oss: no revision, weights hash, or serving-version field
anywhere on disk. Gemma outcome records carry `model_family: "gemma_4_31b"` only.
Notably, unlike LAB-Bench (which pins an upstream dataset revision — see
`licenses.md`), **no model was version-pinned in this project**.

Citation target, `custom.bib`:

```bibtex
@article{gemma4report,
  title = {Gemma 4 Technical Report},
  author = {{Gemma Team}},
  journal = {arXiv preprint arXiv:2607.02770},
  year = {2026},
  url = {https://arxiv.org/abs/2607.02770}
}
```

---

## 3. `google/gemma-3-27b-it` (appendix reduced actor-stack check only)

`no_model_manifest.json`, setting `omnimath2__tier_sampled_833__gemma3_27b`:
`"model_endpoint": "google/gemma-3-27b-it"`, `"run_id": "gemma3_27b"`,
833 matched rows. Confirmed in
`matched_labels/omnimath2__tier_sampled_833__gemma3_27b.csv` row 1.

This backs the appendix table `tab:gemma-actor-scope`, not any main-paper claim.
Snapshot: **UNRESOLVED**, same as above.

---

## 4. Evaluator / judge

The judge is the **same** `openai/gpt-oss-120b`, for both solver families.
Evidence: `hf_reorg2/baseline_llm/omnimath2/gpt_oss_120b/labels/outcomes.jsonl`
record 1 carries `"actor_set_id": "gpt-oss-120b"` and
`"evaluator_id": "gpt-oss-120b"`; the `confident_routing` configs define a
separate `agent_type: evaluator` block whose `model:` is `openai/gpt-oss-120b`
(line 107 of `configs/baseline_llm/config.yaml`).

Cross-family config headers make the fixed-judge design explicit, e.g.
`configs/gemma3_actor/different_model_family/baseline_gemma3_27b_eval_oss120b/config.yaml`
line 3: "paper evaluator fixed on gpt-oss-120b."

The OmniMath pipeline additionally references an `omni-judge` judge type
(`preprocess_omni_math.py` sets `"judge_type": "omni-judge"` on every normalized
record). Which of the two adjudicates a given OmniMath row was **not** resolved
in this session — flag as **UNRESOLVED (judge routing for OmniMath)**; it matters
for anyone re-scoring, and the memory note "verifier version drift across arms"
applies.

---

## 5. Decoding and serving

Verified:

- Temperature **0.0** throughout. `sections/appendix.tex` line 25
  ("probes use deterministic decoding with temperature 0.0"), line 705
  ("temperature 0.0 and a 4096-token per-call generation cap for solver/evaluator"),
  line 770 (frozen routers), line 814, line 874 (256-token completion limit for
  the pre-answer probe). The configs corroborate: `temperature: 0`,
  `max_tokens: 4096`.
- Post-answer probe generation cap **1024** tokens, **4** API retries, **2**
  repair attempts: `jobs/run_gpt_oss_omni_confidence.sh`
  (`MAX_TOKENS="${MAX_TOKENS:-1024}"`, `--max-retries 4`,
  `REPAIR_ATTEMPTS="${REPAIR_ATTEMPTS:-2}"`). Paper agrees,
  `appendix_additional_analyses.tex` line 301.
- Endpoint: ALCF Sophia, OpenAI-compatible vLLM. From
  `<inventory-repo>/dhd-release-worktree/use_alcf.sh`:
  `export OPENAI_BASE_URL="https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1/"`
  (a commented-out `metis` line sits above it, unused).
- Post-review probe and router compute ran on **Aurora** (an HPC project space),
  per the PBS jobs and `no_model_manifest.json` staging paths.
- The endpoint does not enforce structured output:
  `aurora_gpt_oss_omni_addon_status_2026-07-13.md` line 79 — "The endpoint accepts
  but does not enforce `response_format={"type":"json_object"}` for
  `openai/gpt-oss-120b`; `guided_json` is rejected with HTTP 422." This is why the
  probe has a repair-attempt path and a sub-1.0 parse rate (0.9928 → 4,151 of 4,181).

---

## 6. What to write in the release

Recommended, and fully supported by the evidence above:

> Solvers were served through the ALCF Sophia OpenAI-compatible vLLM endpoint as
> `openai/gpt-oss-120b` and `google/gemma-4-31B-it`, with a reduced
> `google/gemma-3-27b-it` actor-stack check in the appendix. The same
> `openai/gpt-oss-120b` served as evaluator for both solver families. All
> generation used temperature 0.0. Provider-side model snapshot identifiers were
> not recorded at run time and cannot be reconstructed from the artifacts;
> runs took place between May and July 2026.

Do not add a version string that no artifact contains.

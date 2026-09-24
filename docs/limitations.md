# Limitations

These limitations come from the paper itself, plus limitations of this public
release. They are stated here so that a first-time reader does not over-read
the artifact.

## Limitations of the study

**One realized execution per problem-protocol pair.** Every problem was run
once under each of the four protocols. The reported intervals are 2,000-resample
problem-level percentile bootstraps: they quantify uncertainty from *which
problems* are in the benchmark, not from re-running a stochastic system. A
protocol that succeeds here might fail on a second sample, and we do not measure
that.

**The fixed-order oracle is retrospective.** It is computed after the fact, by
asking which is the first protocol in the order Baseline -> Single -> PER ->
Broadcast that actually succeeded. It is an upper bound for orientation, not a
policy anyone could deploy, and not an estimate of per-instance expected utility.
It also uses one aggregate cost order rather than per-problem costs.

**Scope of the deeper analyses.** Matched four-protocol outcomes cover all ten
model-condition settings. The post-answer confidence probes, the held-out router
evaluations, and the PER-versus-Broadcast interaction analysis cover only the
six settings formed by both solvers on OmniMath, LAB-Bench strict, and LAB-Bench
text-no-tool. Do not read the six-setting conclusions as holding across all ten.

**The primary router comparison is narrow.** The main routing table and the
pre-answer confidence gate use one solver family on one mathematics benchmark,
with a 423-problem held-out split. The broader settings are targeted robustness
checks, not a claim of general universality.

**Cost is measured in logged tokens.** Latency, monetary price, energy,
parallelism, and answer quality beyond exact correctness are not modeled, and
any of them could change which protocol is preferable in a real deployment.

**Confidence parsing is imperfect.** The post-answer probe excludes unparseable
outputs from its probability metrics (30 of 4,181 in the headline gpt-oss-120b
OmniMath setting). Parse rates and confidence quality vary substantially by model
and by domain; see `results/aggregate/postanswer_confidence.csv`.

**No causal mechanism is identified.** The observed PER-versus-Broadcast
differences describe *that* protocol value varies by task, not *why*. We
deliberately do not offer a mechanism.

## Limitations of this release

**Upstream problem text is not redistributed.** We release stable problem
identifiers and our measured outcomes, not benchmark questions or gold answers.
See `docs/data_schema.md` and the dataset card's reconstruction instructions to
rebuild the inputs from the pinned upstream releases.

**Offline analyses reproduce; protocol execution does not.** Everything in
`make reproduce-tables` runs from released outcomes on a laptop. Re-running the
four protocols themselves requires model endpoints for gpt-oss-120b and
Gemma-4-31B-it and substantial compute; that path is documented but not
reproducible from this repository alone.

**Some aggregate tables are published without a lower-level artifact.** Where
that is the case it is marked explicitly in
the post-review analysis map under `docs/provenance/` and listed in `TODO.md`. We chose
to publish those tables with a stated provenance limitation rather than omit
them or imply a reproducibility we cannot demonstrate.

**Two scoring passes exist for OmniMath.** An earlier scoring pass disagrees
with the camera-ready one on 3 of 4,181 problems. The camera-ready labels are
authoritative and are what this release ships; the difference is documented in
`docs/provenance/` so that a reader who encounters both is not misled.

# Protocol definitions

This page defines every paper-specific term used in the release. No prior
familiarity with the paper or with our internal tooling is assumed.

## The decision this paper studies

Running a language model with more collaboration usually solves more problems,
but it costs more tokens. The practical question is not "is collaboration good"
but **"for this particular problem, is the extra collaboration worth paying
for, and which kind?"** We call a policy that makes that choice *before* seeing
any outcome a **router**.

To study the choice cleanly, every problem is run under all four protocols,
with the solver model held fixed inside each setting. That gives a *matched*
outcome per problem-protocol pair, so protocols can be compared without
confounding them with which problems they happened to see.

## The four protocols

| Protocol | Color | What it does |
|---|---|---|
| **Baseline** | `#4C78A8` | Direct, one-shot solving. The model answers once. |
| **Single** | `#F58518` | Iterative single-agent self-correction: the model revisits and revises its own answer. |
| **PER** | `#54A24B` | Planner-Executor-Reviewer collaboration: three specialized roles. |
| **Broadcast** | `#B279A2` | Multi-agent deliberation: independent candidate generation plus information sharing between agents. |
| *None* | `#9C9C9C` | Not a protocol. See below. |

Costs rise roughly in that order, which is what makes the ordering meaningful.

## The fixed-order oracle

For each problem we ask: *what is the first protocol in this fixed order that
actually succeeded?*

```
Baseline -> Single -> PER -> Broadcast -> None
```

The answer is the problem's **fixed-order oracle label**. **None** means all
four observed protocol executions failed; it is a retrospective oracle/router
*action*, not a fifth protocol that anyone ran.

Three things about the oracle matter and are easy to get wrong:

1. It is **retrospective**. It is computed after the outcomes are known, so no
   deployable policy can achieve it. It is a ceiling for orientation.
2. It is defined over **one matched realized execution per protocol**, not over
   an expectation across repeated stochastic runs.
3. A later protocol succeeding never overrides an earlier one. If Baseline
   succeeded, the label is Baseline, even if Broadcast also succeeded.

## Failure risk versus collaboration value

These are the two prediction problems the paper separates, and the separation
is the paper's central point.

* **Failure risk** - will the *Baseline* answer be wrong? A single binary
  question about one protocol.
* **Collaboration value** - will a more expensive protocol add enough marginal
  solve value to justify escalating, and *which* protocol? A harder,
  protocol-specific question.

The headline result is that a model's own confidence answers the first question
fairly well and the second question poorly. Confidence can support a first-stage
stay-or-escalate decision. It does not solve protocol selection.

## Policies referred to in the paper

* **Self-confidence gate** - keep Baseline if the confidence score is at least
  70; otherwise escalate to Single. That binary policy, and only that policy,
  is what "self-confidence gate" means here.
* **Two-threshold cascade** - a *separate appendix ablation*: Baseline at high
  confidence, Single at intermediate confidence, and Tier-majority at very low
  confidence (thresholds 70 and 10). It is not the self-confidence gate.
* **Tier-majority** - a train-split, metadata-only reference policy. It predicts
  the majority fixed-order oracle label within each difficulty tier, falling
  back to the train-split global majority when a tier is unavailable.
* **Frozen LLM router** - an off-the-shelf model prompted to choose the action,
  with no training on our data.

## Stages of the pipeline

Readers often conflate these; the release keeps them separate.

1. **Protocol execution** - actually running Baseline/Single/PER/Broadcast
   against a model endpoint. Expensive. Not reproducible from this repository.
2. **Matched outcome construction** - assembling one row per problem holding all
   four realized outcomes.
3. **Offline oracle labeling** - applying the fixed order to those outcomes.
4. **Router training** - fitting a policy on *features only*, never on outcomes.
5. **Confidence probing** - asking the solver, after it answers but before any
   collaboration, how confident it is. The probe sees the problem, allowed
   metadata, and the model's own Baseline final answer - and no gold answer, no
   correctness label, no oracle label, and no protocol outcome.
6. **Scoring and evaluation** - comparing predictions against held-out labels.

Steps 2-6 are offline and are what this artifact reproduces.

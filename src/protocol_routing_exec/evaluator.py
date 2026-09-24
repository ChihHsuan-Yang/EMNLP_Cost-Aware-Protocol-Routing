"""The shared LLM-judge evaluator contract used by all four protocols.

Port of ``LlmPerEvaluator`` (agentverse/environments/tasksolving_env/rules/
evaluator/per.py:451-587), the ``type: llm`` evaluator that every paper config
selects.

Three properties of the original are load-bearing and are preserved exactly:

1. BOX GATE. ``box_required = True``. If the submitted candidate contains no
   ``\\boxed{...}``, the judge model is NEVER CALLED: the item short-circuits to
   FAIL with ``direct_protocol_fail=True`` and reason
   ``missing_boxed_final_answer``. A format failure is therefore recorded as a
   wrong answer, and it costs zero judge tokens.

2. TWO CALLS ON FAIL. When the verdict is FAIL and ``include_hint_on_fail`` is
   true, a SECOND judge call generates the repair hint, with the correctness
   verdict explicitly pinned so the second call cannot overturn the first. The
   baseline protocol passes ``include_hint_on_fail=False`` and so makes only
   one call. This asymmetry is a real cost difference between protocols.

3. VERDICT LINE IS NOT PARSED. The prompt asks for ``Verdict: PASS|FAIL``, but
   the runtime parser reads only ``Correctness:``. See parsing.parse_mgsm_evaluator.

Additionally: if the judge response fails to parse ``max_retry`` times, the
original records score 0, i.e. an unparseable judge reads as a WRONG ANSWER
rather than as an error. We reproduce that outcome but, unlike the original,
also set ``judge_unparseable=True`` in the record so it is auditable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .parsing import (
    OutputParserError,
    coerce_evaluator_score,
    extract_boxed,
    extract_final_answer,
    parse_mgsm_evaluator,
)

GENERIC_FAILURE_HINT = (
    "Re-check the answer shape, completeness, and whether the response answers "
    "exactly what the problem asks."
)


def format_evaluator_verdict_only(mode: str, passed: bool) -> str:
    """Port of ``_format_evaluator_verdict_only`` (rules/per.py:309-318)."""
    normalized_mode = str(mode or "unknown").strip() or "unknown"
    signal = "PASS" if passed else "FAIL"
    return "\n".join([
        "Evaluation signal: %s" % signal,
        "Verifier mode: %s" % normalized_mode,
        "Score: %s" % passed,
    ])


def format_evaluator_hint_only(advice: str) -> str:
    """Port of ``_format_evaluator_hint_only`` (rules/per.py:321-323)."""
    clean_advice = str(advice or "").strip()
    return "Evaluation hint: %s" % clean_advice if clean_advice else "Evaluation hint: [none]"


def format_evaluator_feedback(mode: str, passed: bool, advice: str) -> str:
    """Port of ``_format_evaluator_feedback`` (rules/per.py:293-306)."""
    normalized_mode = str(mode or "unknown").strip() or "unknown"
    signal = "PASS" if passed else "FAIL"
    clean_advice = str(advice or "").strip()
    lines = [
        "Evaluation signal: %s" % signal,
        "Verifier mode: %s" % normalized_mode,
        "Score: %s" % passed,
    ]
    lines.append("Hint: %s" % clean_advice if clean_advice
                 else "Hint: Verifier: %s (%s)." % (signal, normalized_mode))
    return "\n".join(lines)


def format_reviewer_feedback(mode: str, passed: bool, advice: str,
                             reviewer_feedback_mode: str) -> str:
    """Port of ``_format_reviewer_feedback`` (rules/per.py:485-517).

    THIS IS THE ``reviewer_feedback_mode`` SWITCH and it is scientifically
    significant. Under ``plain`` (the baseline protocol) the judge's actual
    advice text is DISCARDED and replaced by a canned string; combined with
    ``include_hint_on_fail=False`` the baseline therefore receives no
    information from the judge beyond PASS/FAIL. Under ``hint`` (the other
    three protocols) the real advice flows back into the next attempt.
    """
    normalized_mode = str(mode or "unknown").strip() or "unknown"
    signal = "PASS" if passed else "FAIL"
    feedback_mode = str(reviewer_feedback_mode or "plain").strip().lower() or "plain"

    if feedback_mode == "hint":
        return format_evaluator_feedback(mode, passed, advice)

    if passed:
        plain_advice = "Verifier: PASS (%s)." % normalized_mode
    elif normalized_mode in {"exact", "numeric-verifier", "omni-rule"}:
        plain_advice = ("Verifier: FAIL (%s). Re-check the reasoning and the "
                        "final Reviewer's boxed answer." % normalized_mode)
    else:
        plain_advice = ("Verifier: FAIL (%s). Re-check the reasoning and the "
                        "final reviewer answer." % normalized_mode)

    return "\n".join([
        "Evaluation signal: %s" % signal,
        "Verifier mode: %s" % normalized_mode,
        "Score: %s" % passed,
        "Advice: %s" % plain_advice,
    ])


class EvaluationResult(object):
    """Structured outcome of one evaluator invocation."""

    def __init__(self, passed, final_answer="", ground_truth="", advice="",
                 verdict_advice="", hint_advice="", mode="llm",
                 direct_protocol_fail=False, direct_protocol_fail_reason="",
                 reference_solution_used=False, judge_calls=0,
                 judge_unparseable=False, raw_verdict_text="", raw_hint_text=""):
        self.passed = bool(passed)
        self.final_answer = final_answer
        self.ground_truth = ground_truth
        self.advice = advice
        self.verdict_advice = verdict_advice
        self.hint_advice = hint_advice
        self.mode = mode
        self.direct_protocol_fail = bool(direct_protocol_fail)
        self.direct_protocol_fail_reason = direct_protocol_fail_reason
        self.reference_solution_used = bool(reference_solution_used)
        self.judge_calls = int(judge_calls)
        self.judge_unparseable = bool(judge_unparseable)
        self.raw_verdict_text = raw_verdict_text
        self.raw_hint_text = raw_hint_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "correctness": 1 if self.passed else 0,
            "signal": "PASS" if self.passed else "FAIL",
            "mode": self.mode,
            "final_answer": self.final_answer,
            "advice": self.advice,
            "verdict_advice": self.verdict_advice,
            "hint_advice": self.hint_advice,
            "direct_protocol_fail": self.direct_protocol_fail,
            "direct_protocol_fail_reason": self.direct_protocol_fail_reason,
            "reference_solution_used": self.reference_solution_used,
            "judge_calls": self.judge_calls,
            "judge_unparseable": self.judge_unparseable,
        }


class LlmEvaluator(object):
    """``evaluator.type: llm`` -- an LLM judge under a fixed output contract."""

    mode_name = "llm"
    box_required = True

    def __init__(self, client, prepend_template, append_template,
                 dimensions=None, max_parse_retry=10, max_tokens=4096):
        self.client = client
        self.prepend_template = prepend_template
        self.append_template = append_template
        self.dimensions = list(dimensions or ["Correctness"])
        self.max_parse_retry = int(max_parse_retry)
        self.max_tokens = int(max_tokens)

    def _render(self, task_description, solution, result) -> List[Dict[str, str]]:
        from string import Template
        mapping = {
            "task_description": task_description,
            "solution": solution,
            "result": result,
        }
        prepend = Template(self.prepend_template).safe_substitute(mapping)
        append = Template(self.append_template).safe_substitute(mapping)
        return [{"role": "user", "content": (prepend + "\n\n" + append).strip()}]

    def _call_judge(self, messages, role):
        """One judge call plus in-process reparse retries.

        The original retries the WHOLE call (prompt + parse) up to max_retry
        times inside EvaluatorAgent.astep and records score 0 on exhaustion.
        """
        last_text = ""
        for _ in range(max(1, self.max_parse_retry)):
            response = self.client.complete(messages, role=role,
                                            max_tokens=self.max_tokens)
            last_text = response.content
            if response.error:
                continue
            try:
                passed, advice = parse_mgsm_evaluator(last_text, self.dimensions)
                return passed, advice, last_text, False
            except OutputParserError:
                continue
        # Exhausted: upstream behaviour is score 0 == FAIL, empty advice.
        return False, "", last_text, True

    def evaluate(self, task_description, submitted_candidate, ground_truth,
                 reference_solution="", include_hint_on_fail=True,
                 previous_answer_summary="", previous_reasoning_summary="",
                 current_reasoning_summary="") -> EvaluationResult:
        submitted_candidate = str(submitted_candidate or "").strip()
        ground_truth = str(ground_truth or "")
        reference_solution = str(reference_solution or "").strip()
        ground_truth_final = extract_final_answer(ground_truth)

        # --- 1. Box gate. No judge call when there is no boxed answer. -----
        boxed = extract_boxed(submitted_candidate)
        if self.box_required and not boxed:
            hint = ("System protocol check: FAIL. "
                    "No boxed final answer was found in the submitted solution, so the "
                    "evaluator was not called. Please resubmit with exactly one clear "
                    "boxed final answer. Try to keep the reasoning concise and finish "
                    "the solution within the available output window.")
            return EvaluationResult(
                passed=False, final_answer="", ground_truth=ground_truth_final,
                advice=hint, verdict_advice="System protocol check: FAIL.",
                hint_advice=hint, mode=self.mode_name, direct_protocol_fail=True,
                direct_protocol_fail_reason="missing_boxed_final_answer",
                reference_solution_used=bool(reference_solution), judge_calls=0)

        candidate = "\\boxed{%s}" % boxed
        final_answer = extract_final_answer(candidate)

        judge_submission = ("Current extracted MAS final answer for this evaluator attempt:\n"
                            "%s" % candidate)
        result_blocks = ["Ground truth final answer:\n%s" % ground_truth]
        if reference_solution:
            result_blocks.append(
                "Reference solution for evaluator-only use. Use it to judge equivalence "
                "and diagnose mismatch type, but do not reveal, quote, or restate it:\n"
                "%s" % reference_solution)
        result_text = "\n\n".join(result_blocks)

        # --- 2. Verdict call ------------------------------------------------
        messages = self._render(task_description, judge_submission, result_text)
        passed, evaluator_feedback, raw_verdict, unparseable = self._call_judge(
            messages, role="evaluator_verdict")
        passed = coerce_evaluator_score(passed)
        evaluator_feedback = str(evaluator_feedback or "").strip()
        verdict_advice = evaluator_feedback or (
            "Answer judged equivalent to the reference answer." if passed
            else "The answer is not equivalent to the reference answer. %s" % GENERIC_FAILURE_HINT)

        hint_advice = ""
        judge_calls = 1
        raw_hint = ""

        # --- 3. Hint call, FAIL only, verdict pinned -------------------------
        if (not passed) and include_hint_on_fail:
            hint_submission = (
                "%s\n\n"
                "The boxed final answer above has already been judged incorrect.\n"
                "Generate a more useful non-leaking repair hint.\n"
                "Do NOT change or reconsider the correctness verdict." % judge_submission)
            hint_blocks = list(result_blocks) + [
                "Correctness is already fixed to FAIL based on the boxed final answer above. "
                "Use the reference material and the structured context only to diagnose the "
                "mismatch type and produce a brief non-leaking repair hint."]
            history = self._build_hint_history(
                previous_answer_summary, previous_reasoning_summary,
                candidate, current_reasoning_summary or submitted_candidate)
            hint_messages = history + self._render(
                task_description, hint_submission, "\n\n".join(hint_blocks))
            _, hint_feedback, raw_hint, hint_unparseable = self._call_judge(
                hint_messages, role="evaluator_hint")
            judge_calls = 2
            unparseable = unparseable or hint_unparseable
            hint_advice = (str(hint_feedback or "").strip() or evaluator_feedback
                           or "The answer is not equivalent to the reference answer. %s"
                           % GENERIC_FAILURE_HINT)

        advice = hint_advice if hint_advice else verdict_advice

        return EvaluationResult(
            passed=passed, final_answer=final_answer, ground_truth=ground_truth_final,
            advice=advice, verdict_advice=verdict_advice, hint_advice=hint_advice,
            mode=self.mode_name, reference_solution_used=bool(reference_solution),
            judge_calls=judge_calls, judge_unparseable=unparseable,
            raw_verdict_text=raw_verdict, raw_hint_text=raw_hint)

    @staticmethod
    def _build_hint_history(previous_answer_summary, previous_reasoning_summary,
                            current_answer, current_reasoning) -> List[Dict[str, str]]:
        """Port of ``_build_hint_history`` (rules/evaluator/per.py:102-131).

        Injected as system messages so the hint generator can see the attempt
        trajectory without re-reading the full transcript.
        """
        blocks = []
        if previous_answer_summary:
            blocks.append("Previous answers for this question:\n%s" % previous_answer_summary)
        if previous_reasoning_summary:
            blocks.append("Previous reasoning trajectory:\n%s" % previous_reasoning_summary)
        if current_answer:
            blocks.append("Current answer under review:\n%s" % current_answer)
        if current_reasoning:
            blocks.append("Current reasoning under review:\n%s" % str(current_reasoning)[:4000])
        return [{"role": "system", "content": block} for block in blocks]

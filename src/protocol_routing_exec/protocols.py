"""The four collaboration protocol drivers.

Each driver is a port of one rule class from the original engine:

  baseline  <- rules/single_llm_benchmark.py::SingleLLMBenchmarkRule
  single    <- rules/single_agent_reflect.py::SingleAgentReflectRule
  per       <- rules/per.py::PerRule
  broadcast <- rules/broadcast_deliberation.py::BroadcastDeliberationRule

All four share one outer loop, ported from agentverse/tasksolving.py::run:

    while not done:  step(advice, previous_plan)   # done = success or max_rounds

Every driver returns a ProtocolOutcome carrying the final answer, the PASS/FAIL
verdict, the per-role token ledger, and a structured event log.

SIMPLIFICATIONS relative to the original engine are marked ``SIMPLIFICATION:``
in comments here and are catalogued in docs/track_b_requirements.md. The
important ones are: no rolling LLM chat-history summarisation, no token-budget
trimming of prompt sections, and sequential rather than concurrent broadcast
polling.
"""

from __future__ import annotations

from string import Template
from typing import Any, Callable, Dict, List, Optional

from .evaluator import (
    LlmEvaluator,
    format_evaluator_hint_only,
    format_evaluator_verdict_only,
    format_reviewer_feedback,
)
from .memory import (
    CandidateRevisionMemory,
    FailedAttemptMemory,
    compact_text,
    with_authority_guide,
)
from .parsing import (
    coerce_bool_value,
    default_fail_route,
    extract_boxed,
    extract_int_field,
    extract_json_object,
    extract_labeled_boxed,
    extract_reviewer_submission_candidate,
    is_meaningful_public_text,
    normalize_boxed,
    parse_route,
    submitted_final_answer_for_trace,
)


class ProtocolOutcome(object):
    def __init__(self, final_answer="", final_text="", passed=False, rounds_used=0,
                 events=None, evaluations=None, stop_reason=""):
        self.final_answer = final_answer
        self.final_text = final_text
        self.passed = bool(passed)
        self.rounds_used = int(rounds_used)
        self.events = events or []
        self.evaluations = evaluations or []
        self.stop_reason = stop_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "passed": self.passed,
            "correctness": 1 if self.passed else 0,
            "rounds_used": self.rounds_used,
            "stop_reason": self.stop_reason,
            "n_events": len(self.events),
            "evaluations": [e.to_dict() for e in self.evaluations],
        }


def _render(template: str, mapping: Dict[str, str]) -> str:
    """Substitute ``${placeholder}`` tokens, leaving unknown ones intact.

    Matches the original engine, which uses string.Template.safe_substitute
    for every agent prompt.
    """
    return Template(str(template or "")).safe_substitute(
        {k: ("" if v is None else str(v)) for k, v in mapping.items()})


class BaseProtocol(object):
    """Shared plumbing: outer loop, logging, evaluator wiring."""

    protocol_id = "base"

    def __init__(self, spec, clients, evaluator, logger=None):
        self.spec = spec
        self.clients = clients          # role name -> ChatClient
        self.evaluator = evaluator      # LlmEvaluator
        self.logger = logger or (lambda msg: None)
        self.max_rounds = int(spec.get("max_rounds", 1))
        rule = spec.get("rule", {}) or {}
        self.rule = rule
        self.reviewer_feedback_mode = str(rule.get("reviewer_feedback_mode", "plain"))
        self.include_hint_on_fail = bool(rule.get("include_hint_on_fail", True))
        self.failed_attempt_memory = FailedAttemptMemory(
            int(rule.get("failed_attempt_memory_limit", 3)))
        self.candidate_revision_memory = CandidateRevisionMemory(
            int(rule.get("candidate_revision_memory_limit", 5)))

    # -- helpers ----------------------------------------------------------

    def client_for(self, role: str):
        if role not in self.clients:
            raise KeyError("No client configured for role %r (have %s)"
                           % (role, sorted(self.clients)))
        return self.clients[role]

    def prompts_for(self, role: str) -> Dict[str, str]:
        return (self.spec.get("roles", {}) or {}).get(role, {}) or {}

    def call_role(self, role: str, mapping: Dict[str, str], events: List[Dict[str, Any]],
                  stage: str, dry_run=False) -> str:
        """Render this role's prompt pair and issue one call."""
        role_spec = self.prompts_for(role)
        prepend = _render(role_spec.get("prepend_prompt", ""), mapping)
        append = _render(role_spec.get("append_prompt", ""), mapping)
        content = (prepend + "\n\n" + append).strip()
        if dry_run:
            events.append({"type": "dry_run_prompt", "stage": stage, "role": role,
                           "prompt": content})
            return ""
        result = self.client_for(role).complete(
            [{"role": "user", "content": content}], role=role,
            max_tokens=role_spec.get("max_tokens"))
        text = result.content or ""
        events.append({
            "type": "message", "stage": stage, "role": role,
            "sender": role_spec.get("name", role), "content": text,
            "tokens": {"prompt": result.send_tokens, "completion": result.recv_tokens},
            "error": result.error, "attempts": result.attempts,
        })
        if result.error:
            self.logger("[%s] role=%s stage=%s call failed: %s"
                        % (self.protocol_id, role, stage, result.error))
        return text

    def run_evaluation(self, problem, candidate, events, stage, current_reasoning=""):
        events.append({
            "type": "message", "stage": "%s_submission" % stage, "role": "system",
            "sender": "system",
            "content": ("Actual extracted final answer sent to evaluator: %s"
                        % submitted_final_answer_for_trace(candidate)),
        })
        evaluation = self.evaluator.evaluate(
            task_description=problem["input"],
            submitted_candidate=candidate,
            ground_truth=problem["answer"],
            reference_solution=problem.get("reference_solution", ""),
            include_hint_on_fail=self.include_hint_on_fail,
            previous_answer_summary=self.failed_attempt_memory.render_for_evaluator_hint(),
            previous_reasoning_summary=self.candidate_revision_memory.render_for_evaluator_hint(),
            current_reasoning_summary=current_reasoning or candidate,
        )
        events.append({
            "type": "meta", "stage": "%s_result" % stage, "role": "evaluator",
            "sender": "system" if evaluation.direct_protocol_fail else "Evaluator",
            "content": format_evaluator_verdict_only(evaluation.mode, evaluation.passed),
            **evaluation.to_dict(),
        })
        if (not evaluation.passed) and evaluation.hint_advice:
            events.append({
                "type": "message", "stage": "%s_hint" % stage, "role": "evaluator",
                "sender": "Evaluator",
                "content": format_evaluator_hint_only(evaluation.hint_advice),
            })
        return evaluation

    def feedback_text(self, evaluation) -> str:
        return format_reviewer_feedback(
            evaluation.mode, evaluation.passed,
            evaluation.hint_advice or evaluation.verdict_advice or evaluation.advice,
            self.reviewer_feedback_mode)

    def advice_with_question_memory(self, advice: str) -> str:
        """Port of ``_advice_with_question_memory``."""
        clean = str(advice or "").strip()
        parts = []
        if clean:
            parts.append(clean)
        if self.candidate_revision_memory.records:
            parts.append(self.candidate_revision_memory.render())
        if self.failed_attempt_memory.records:
            parts.append(self.failed_attempt_memory.render())
        combined = "\n\n".join(p for p in parts if str(p).strip()).strip()
        return with_authority_guide(combined) if combined else ""

    # -- outer loop -------------------------------------------------------

    def run(self, problem, dry_run=False) -> ProtocolOutcome:
        """Port of TaskSolving.run: iterate rounds until success or max_rounds."""
        self.failed_attempt_memory.reset()
        self.candidate_revision_memory.reset()
        events: List[Dict[str, Any]] = []
        evaluations = []
        advice = ""
        previous_plan = ""
        final_text = ""
        passed = False
        rounds_used = 0
        stop_reason = "max_rounds_exhausted"

        for round_id in range(self.max_rounds):
            rounds_used = round_id + 1
            result_text, advice, previous_plan, passed, evaluation = self.step(
                problem, advice, previous_plan, round_id, events, dry_run=dry_run)
            final_text = result_text
            if evaluation is not None:
                evaluations.append(evaluation)
            if dry_run:
                stop_reason = "dry_run"
                break
            if passed:
                stop_reason = "evaluator_pass"
                break

        return ProtocolOutcome(
            final_answer=extract_boxed(final_text), final_text=final_text,
            passed=passed, rounds_used=rounds_used, events=events,
            evaluations=evaluations, stop_reason=stop_reason)

    def step(self, problem, advice, previous_plan, round_id, events, dry_run=False):
        raise NotImplementedError


# ===========================================================================
# 1. BASELINE  -- one solver call, one judge call, no feedback, no retry
# ===========================================================================

class BaselineProtocol(BaseProtocol):
    """Port of SingleLLMBenchmarkRule.

    max_rounds is 1, so the outer loop runs exactly once regardless of the
    verdict. reviewer_feedback_mode is forced to "plain" by the original rule
    (single_llm_benchmark.py:44) even if the config says otherwise, because
    the solver never reads it. include_hint_on_fail is False, so the judge is
    called ONCE, not twice. Both facts are encoded in the shipped config.
    """

    protocol_id = "baseline"

    def __init__(self, *args, **kwargs):
        super(BaselineProtocol, self).__init__(*args, **kwargs)
        # Upstream hard-codes this regardless of config (single_llm_benchmark.py:44).
        self.reviewer_feedback_mode = "plain"

    def step(self, problem, advice, previous_plan, round_id, events, dry_run=False):
        solver_text = self.call_role("solver", {
            "task_description": problem["input"],
            "advice": "", "former_solution": "", "previous_plan": "",
            "role_description": self.prompts_for("solver").get("role_description", ""),
        }, events, stage="solver", dry_run=dry_run)

        if dry_run:
            return "", "", "", False, None

        candidate = solver_text.strip() or "[No solver output]"
        evaluation = self.run_evaluation(problem, candidate, events, "evaluation",
                                         current_reasoning=solver_text)
        return candidate, self.feedback_text(evaluation), candidate, evaluation.passed, evaluation


# ===========================================================================
# 2. SINGLE   -- one solver iterating on evaluator hints, up to max_rounds
# ===========================================================================

class SingleAgentProtocol(BaseProtocol):
    """Port of SingleAgentReflectRule.

    Key behaviours:
      * ``reset_solver_memory_each_attempt`` (default true): the solver's chat
        history is cleared before every attempt, so the ONLY carry-over between
        attempts is the structured question-scoped ledger, not a transcript.
      * the first attempt uses a distinct prompt pair
        (``first_attempt_prepend_prompt``), because there is no prior answer or
        feedback to reference.
      * reviewer_feedback_mode is "hint", so the judge's real repair hint is
        fed back.
    """

    protocol_id = "single"

    def step(self, problem, advice, previous_plan, round_id, events, dry_run=False):
        former_solution = str(previous_plan or "").strip()
        normalized_advice = str(advice or "").strip()
        is_first = (not former_solution and not normalized_advice
                    and not self.failed_attempt_memory.records
                    and not self.candidate_revision_memory.records)

        role_spec = self.prompts_for("solver")
        mapping = {
            "task_description": problem["input"],
            "former_solution": former_solution,
            "previous_plan": former_solution,
            "advice": self.advice_with_question_memory(normalized_advice),
            "role_description": role_spec.get("role_description", ""),
        }

        if is_first and role_spec.get("first_attempt_prepend_prompt"):
            prepend = _render(role_spec["first_attempt_prepend_prompt"], mapping)
            append = _render(role_spec.get("first_attempt_append_prompt", ""), mapping)
            content = (prepend + "\n\n" + append).strip()
            if dry_run:
                events.append({"type": "dry_run_prompt", "stage": "solver_first_attempt",
                               "role": "solver", "prompt": content})
                return "", "", "", False, None
            result = self.client_for("solver").complete(
                [{"role": "user", "content": content}], role="solver",
                max_tokens=role_spec.get("max_tokens"))
            solver_text = result.content or ""
            events.append({"type": "message", "stage": "solver_first_attempt",
                           "role": "solver", "sender": role_spec.get("name", "Solo"),
                           "content": solver_text,
                           "tokens": {"prompt": result.send_tokens,
                                      "completion": result.recv_tokens},
                           "error": result.error, "attempts": result.attempts})
        else:
            solver_text = self.call_role("solver", mapping, events,
                                         stage="solver_attempt_%d" % round_id,
                                         dry_run=dry_run)
            if dry_run:
                return "", "", "", False, None

        candidate = solver_text.strip() or "[No solver output]"
        proposal = self.candidate_revision_memory.add(
            stage="solver", source=role_spec.get("name", "Solo"), action="propose",
            candidate_answer=candidate, rationale_or_review=solver_text)
        self.candidate_revision_memory.add(
            stage="submission", source="system", action="submit",
            candidate_answer=candidate, rationale_or_review="Submitted to evaluator.",
            parent_event_id=proposal["event_id"] if proposal else None)

        evaluation = self.run_evaluation(problem, candidate, events, "evaluation",
                                         current_reasoning=solver_text)
        feedback = self.feedback_text(evaluation)

        self.candidate_revision_memory.add(
            stage="evaluation", source="Evaluator", action="evaluate",
            candidate_answer=("\\boxed{%s}" % evaluation.final_answer
                              if evaluation.final_answer else candidate),
            rationale_or_review=feedback,
            evaluator_signal="PASS" if evaluation.passed else "FAIL")

        if not evaluation.passed:
            submitted = evaluation.final_answer or candidate
            self.failed_attempt_memory.add(
                submitted_answer=submitted,
                evaluator_signal="FAIL", evaluator_hint=feedback,
                repair_summary=(
                    "Rejected answer: %s\nEvaluator feedback to address: %s\n"
                    "Next attempt goal: produce a new complete answer that addresses "
                    "the evaluator feedback and do not repeat the same rejected answer "
                    "unless the mismatch has been resolved."
                    % (compact_text(submitted, 180) or "[no extracted answer]",
                       compact_text(feedback, 260) or "[no evaluator feedback]")),
                source_stage="evaluation")

        return candidate, feedback, candidate, evaluation.passed, evaluation


# ===========================================================================
# 3. PER  -- Planner / Executor / Reviewer with an inner loop and a repair pass
# ===========================================================================

class PerProtocol(BaseProtocol):
    """Port of PerRule.

    Control flow of one outer round:

      for k in range(inner_rounds):
          if next_actor == planner:  Planner -> Executor
          else:                      Executor
          Reviewer -> route in {Agree, Route:Planner, Route:Executor}
          if route == Agree and stop_on_agree: break
      evaluate(current_candidate)
      if FAIL:
          Planner (repair) -> Executor (repair) -> Reviewer -> evaluate again

    So a single FAILING outer round can issue up to inner_rounds*3 + 3 actor
    calls plus 2 evaluations (each of which is itself up to 2 judge calls).
    This is why PER is the second most expensive protocol per problem.

    SIMPLIFICATION: the original shares a chat history between Planner and
    Reviewer (``_broadcast_to_agents``) with rolling LLM summarisation. Here
    the plan / execution / review texts are passed explicitly through prompt
    placeholders instead. See docs/track_b_requirements.md.
    """

    protocol_id = "per"

    def __init__(self, *args, **kwargs):
        super(PerProtocol, self).__init__(*args, **kwargs)
        self.inner_rounds = int(self.rule.get("inner_rounds", 2))
        self.stop_on_agree = bool(self.rule.get("stop_on_agree", True))
        self.allow_reviewer_override = bool(self.rule.get("allow_reviewer_override", False))

    def _inner_loop(self, problem, advice, previous_plan, round_id, events, dry_run):
        last_plan = str(previous_plan or "")
        last_exec = ""
        last_review = ""
        current_candidate = ""
        next_actor = "planner"
        queued_planner_advice = ""
        queued_executor_advice = ""

        route_in_advice = parse_route(advice or "")
        if route_in_advice == "planner":
            queued_planner_advice, next_actor = advice, "planner"
        elif route_in_advice == "executor":
            queued_executor_advice, next_actor = advice, "executor"
        elif "Verifier: FAIL" in (advice or ""):
            queued_planner_advice, next_actor = advice, "planner"

        for k in range(self.inner_rounds):
            reviewer_advice = advice
            if next_actor == "planner":
                planner_advice = self.advice_with_question_memory(
                    queued_planner_advice or advice)
                plan_text = self.call_role("planner", {
                    "task_description": problem["input"],
                    "previous_plan": last_plan, "former_solution": last_plan,
                    "advice": planner_advice,
                    "role_description": self.prompts_for("planner").get("role_description", ""),
                }, events, stage="planner_%d" % k, dry_run=dry_run)
                if dry_run:
                    # Render one prompt per role, then stop.
                    self.call_role("executor", {
                        "task_description": problem["input"], "solution": last_plan,
                        "advice": "",
                        "role_description": self.prompts_for("executor").get("role_description", ""),
                    }, events, stage="executor_%d" % k, dry_run=True)
                    self.call_role("reviewer", {
                        "task_description": problem["input"],
                        "preliminary_solution": "[executor output]",
                        "previous_plan": last_plan, "advice": "",
                        "all_roles": "Planner / Executor / Reviewer",
                        "role_description": self.prompts_for("reviewer").get("role_description", ""),
                    }, events, stage="reviewer_%d" % k, dry_run=True)
                    return "", "", "", "", "dry_run"
                queued_planner_advice = ""
                last_plan = plan_text or last_plan
                reviewer_advice = planner_advice
                exec_text = self.call_role("executor", {
                    "task_description": problem["input"], "solution": last_plan,
                    "advice": "",
                    "role_description": self.prompts_for("executor").get("role_description", ""),
                }, events, stage="executor_%d" % k)
            else:
                exec_advice = self.advice_with_question_memory(
                    queued_executor_advice or advice)
                exec_text = self.call_role("executor", {
                    "task_description": problem["input"], "solution": last_plan,
                    "advice": exec_advice,
                    "role_description": self.prompts_for("executor").get("role_description", ""),
                }, events, stage="executor_%d" % k, dry_run=dry_run)
                if dry_run:
                    return "", "", "", "", "dry_run"
                queued_executor_advice = ""
                reviewer_advice = exec_advice

            exec_text = exec_text or "[No execution output]"
            last_exec = exec_text
            if extract_boxed(exec_text) or (not current_candidate and exec_text.strip()):
                current_candidate = exec_text.strip()
            self.candidate_revision_memory.add(
                stage="executor_%d" % k, source="Executor", action="propose",
                candidate_answer=exec_text, rationale_or_review=exec_text)

            review_text = self.call_role("reviewer", {
                "task_description": problem["input"],
                "preliminary_solution": last_exec, "previous_plan": last_plan,
                "advice": self.advice_with_question_memory(reviewer_advice),
                "all_roles": "Planner / Executor / Reviewer",
                "role_description": self.prompts_for("reviewer").get("role_description", ""),
            }, events, stage="reviewer_%d" % k)
            last_review = review_text
            route = parse_route(review_text)

            reviewer_candidate = ""
            if route in {"agree", "evaluate"}:
                reviewer_candidate = extract_reviewer_submission_candidate(review_text)
                if reviewer_candidate:
                    current_candidate = reviewer_candidate
            self.candidate_revision_memory.add(
                stage="reviewer_%d" % k, source="Reviewer",
                action="review_submit" if reviewer_candidate else "review_route",
                candidate_answer=reviewer_candidate, rationale_or_review=review_text)

            if route in ("agree", "evaluate") and self.stop_on_agree:
                break
            if route == "planner":
                queued_planner_advice, next_actor = review_text, "planner"
            else:
                # Upstream default for "executor" AND for an unparseable route.
                queued_executor_advice, next_actor = review_text, "executor"

        return last_plan, last_exec, last_review, current_candidate, ""

    def step(self, problem, advice, previous_plan, round_id, events, dry_run=False):
        last_plan, last_exec, last_review, current_candidate, flag = self._inner_loop(
            problem, advice, previous_plan, round_id, events, dry_run)
        if dry_run or flag == "dry_run":
            return "", "", "", False, None

        submission = (current_candidate or last_exec or "").strip()
        evaluation = self.run_evaluation(problem, submission, events, "evaluation",
                                         current_reasoning=last_exec)
        feedback = self.feedback_text(evaluation)
        final_success = evaluation.passed
        latest_eval_feedback = feedback
        next_round_guidance = ""
        latest_reviewer_output = last_review

        if not evaluation.passed:
            # --- in-round repair pass: Planner -> Executor -> Reviewer -> eval
            self.failed_attempt_memory.add(
                submitted_answer=(evaluation.final_answer or submission),
                evaluator_signal="FAIL", evaluator_hint=feedback,
                repair_summary="Pending Planner repair plan.",
                source_stage="initial_evaluation")

            repair_plan = self.call_role("planner", {
                "task_description": problem["input"], "previous_plan": last_plan,
                "former_solution": last_plan,
                "advice": self.advice_with_question_memory(feedback),
                "role_description": self.prompts_for("planner").get("role_description", ""),
            }, events, stage="planner_post_eval_fail")
            self.failed_attempt_memory.update_latest_repair_summary(repair_plan)
            next_round_guidance = (repair_plan or "").strip()
            last_plan = repair_plan or last_plan

            repair_instruction = ("Current internal Planner repair plan (not evaluator "
                                  "ground truth):\n%s" % ((repair_plan or "").strip() or feedback))
            repair_exec = self.call_role("executor", {
                "task_description": problem["input"], "solution": last_plan,
                "advice": "\n\n".join([feedback.strip(), repair_instruction]).strip(),
                "role_description": self.prompts_for("executor").get("role_description", ""),
            }, events, stage="executor_post_eval_fail") or "[No execution output]"
            last_exec = repair_exec
            if extract_boxed(repair_exec) or (not current_candidate and repair_exec.strip()):
                current_candidate = repair_exec.strip()

            repair_review = self.call_role("reviewer", {
                "task_description": problem["input"],
                "preliminary_solution": last_exec, "previous_plan": last_plan,
                "advice": self.advice_with_question_memory(
                    "\n\n".join([feedback.strip(), repair_instruction]).strip()),
                "all_roles": "Planner / Executor / Reviewer",
                "role_description": self.prompts_for("reviewer").get("role_description", ""),
            }, events, stage="reviewer_post_eval_fail")
            latest_reviewer_output = repair_review or latest_reviewer_output
            repair_candidate = extract_reviewer_submission_candidate(repair_review)
            if repair_candidate:
                current_candidate = repair_candidate

            repair_submission = (current_candidate or last_exec or "").strip()
            repair_eval = self.run_evaluation(problem, repair_submission, events,
                                              "repair_evaluation",
                                              current_reasoning=last_exec)
            final_success = repair_eval.passed
            latest_eval_feedback = self.feedback_text(repair_eval)
            evaluation = repair_eval
            if not repair_eval.passed:
                self.failed_attempt_memory.add(
                    submitted_answer=(repair_eval.final_answer or repair_submission),
                    evaluator_signal="FAIL", evaluator_hint=latest_eval_feedback,
                    repair_summary=repair_review, source_stage="repair_evaluation")
                if parse_route(latest_reviewer_output) not in {"planner", "executor"}:
                    forced = default_fail_route(latest_eval_feedback, latest_reviewer_output)
                    latest_reviewer_output = ("%s\n%s"
                                              % ((latest_reviewer_output or "").strip(), forced))
                    next_round_guidance = latest_reviewer_output

            if (self.allow_reviewer_override and not evaluation.passed
                    and "[Agree]" in (repair_plan or "")):
                final_success = True

        if final_success:
            final_advice = latest_eval_feedback
        else:
            parts = [latest_eval_feedback, "[Candidate]",
                     compact_text(current_candidate or latest_reviewer_output, 400),
                     "[EndCandidate]"]
            if next_round_guidance and next_round_guidance != latest_reviewer_output:
                parts.append(next_round_guidance)
            final_advice = "\n".join(p for p in parts if str(p).strip()).strip()

        final_result = current_candidate or latest_reviewer_output or "[No candidate submitted]"
        return final_result, final_advice, (last_plan or ""), final_success, evaluation


# ===========================================================================
# 4. BROADCAST -- N peers, confidence poll, one speaker, approval voting
# ===========================================================================

class BroadcastProtocol(BaseProtocol):
    """Port of BroadcastDeliberationRule.

    One outer round:

      for turn in range(discussion_rounds):
          every peer POLLS (JSON: score 1-100, reason, intent, candidate)
          highest score speaks publicly; peers at or above speak_threshold that
            did not win record a private deferred note
          if a candidate emerged:
              approval loop, up to approval_rounds:
                  every peer votes approve/reject with an optional revision
                  unanimous approval -> consensus, break
                  else candidate <- majority revision
      if still no candidate: final proposal round (highest confidence wins)
      evaluate

    Cost note: the poll is issued to EVERY peer on EVERY turn, so peer count
    multiplies token cost even though only one peer speaks. With 3 peers,
    4 discussion rounds and 2 approval rounds, one outer round can reach
    3*4 polls + 4 speeches + 3*2 approval votes = 22 actor calls.

    SIMPLIFICATION: the original issues polls and approval votes CONCURRENTLY
    with asyncio.gather. This port issues them sequentially. Same calls, same
    content, in a deterministic order; only wall-clock differs.
    """

    protocol_id = "broadcast"

    def __init__(self, *args, **kwargs):
        super(BroadcastProtocol, self).__init__(*args, **kwargs)
        self.discussion_rounds = int(self.rule.get("discussion_rounds", 4))
        self.approval_rounds = int(self.rule.get("approval_rounds", 2))
        self.speak_threshold = int(self.rule.get("speak_threshold", 60))
        self.memory_mode = str(self.rule.get("memory_mode", "summary_plus_recent"))
        self.recent_history_window = int(self.rule.get("recent_history_window", 4))
        self.approval_policy = str(self.rule.get("approval_policy", "unanimous")).lower()
        self.candidate_selection_policy = str(
            self.rule.get("candidate_selection_policy", "majority_revision")).lower()
        self.discussion_instruction = str(self.rule.get("discussion_instruction", "") or (
            "Contribute one focused message to the peer math discussion. "
            "Avoid repeating points already made. "
            "If you believe the group is ready to consider a concrete final answer, "
            "remember that the answer may be numeric, symbolic, formulaic, set-valued, "
            "or conditional, and include a short section exactly in this form:\n"
            "Candidate Answer:\n\\boxed{...}"))
        self.peers = list(self.spec.get("peers", []) or [])
        self.public_history: List[str] = []
        self.private_notes: Dict[str, List[str]] = {}
        self.speak_history: Dict[str, List[str]] = {}

    # -- peer context -----------------------------------------------------

    def _public_context(self) -> str:
        """``memory_mode`` shapes what each peer sees of the shared channel.

        SIMPLIFICATION: "summary_plus_recent" upstream means an LLM-generated
        rolling summary PLUS the last N messages. Here the summary half is
        replaced by a truncated concatenation of older messages -- no extra
        model call. This changes what peers see in long discussions.
        """
        if not self.public_history:
            return "[No public discussion yet.]"
        window = max(1, self.recent_history_window)
        recent = self.public_history[-window:]
        older = self.public_history[:-window]
        blocks = []
        if older and self.memory_mode == "summary_plus_recent":
            joined = " | ".join(compact_text(item, 160) for item in older)
            blocks.append("Earlier discussion (condensed): %s" % compact_text(joined, 800))
        blocks.extend(recent)
        return "\n\n".join(blocks)

    def _private_context(self, peer_name: str) -> str:
        notes = self.private_notes.get(peer_name, [])
        return "\n".join(notes[-5:]) if notes else "[No deferred notes.]"

    def _speak_history(self, peer_name: str) -> str:
        spoken = self.speak_history.get(peer_name, [])
        return "\n".join(spoken[-5:]) if spoken else "[You have not spoken yet.]"

    def _peer_mapping(self, peer, problem, advice, candidate, phase,
                      phase_instruction, turn_label) -> Dict[str, str]:
        return {
            "task_description": problem["input"],
            "advice": self.advice_with_question_memory(advice),
            "candidate_answer": candidate or "[None yet]",
            "role_description": peer.get("role_description", ""),
            "private_memory": self._private_context(peer["name"]),
            "current_turn_label": turn_label,
            "own_speak_history": self._speak_history(peer["name"]),
            "phase": phase,
            "phase_instruction": phase_instruction,
            "public_context": self._public_context(),
            "agent_name": peer["name"],
        }

    def _peer_call(self, peer, prompt_text, events, stage):
        result = self.client_for("deliberator").complete(
            [{"role": "user", "content": prompt_text}], role="deliberator",
            max_tokens=(self.prompts_for("deliberator") or {}).get("max_tokens"))
        events.append({"type": "message", "stage": stage, "role": "deliberator",
                       "sender": peer["name"], "content": result.content,
                       "tokens": {"prompt": result.send_tokens,
                                  "completion": result.recv_tokens},
                       "error": result.error, "attempts": result.attempts})
        return result.content or ""

    # -- poll / approve prompts (ported from deliberator.py) ---------------

    def _poll_prompt(self, peer, problem, advice, candidate, turn_label,
                     round_id, turn_idx) -> str:
        mapping = self._peer_mapping(peer, problem, advice, candidate, "poll",
                                     "", turn_label)
        return (
            "You are %(name)s, one peer in a small math deliberation group.\n\n"
            "Problem:\n%(task)s\n\n"
            "Outer-loop feedback:\n%(advice)s\n\n"
            "Current MAS candidate answer:\n%(candidate)s\n\n"
            "Your reasoning style:\n%(role)s\n\n"
            "Public discussion context:\n%(public)s\n\n"
            "Your deferred private notes:\n%(private)s\n\n"
            "Your own speaking history:\n%(spoken)s\n\n"
            "Current turn label:\n%(label)s\n\n"
            "Current outer round: %(round)d\nCurrent discussion turn: %(turn)d\n\n"
            "This is the mandatory turn-allocation poll. Your numeric confidence score "
            "is used to decide who gets to speak next.\n"
            "You must provide an integer confidence score from 1 to 100.\n"
            "If you do not provide a valid score in the required JSON format, your poll "
            "may be treated as score 1.\n\n"
            "Return a JSON object with exactly these keys:\n"
            '- "score": integer from 1 to 100 for how strongly you want to speak now\n'
            '- "reason": short reason for the score\n'
            '- "intent": what you would say if selected\n'
            '- "candidate_answer": your current best final answer in boxed form, or empty '
            'string if you do not want to propose one now\n'
            '- "has_candidate_answer": true or false\n\n'
            "Return JSON only. Do not add any extra prose before or after the JSON object.\n"
            "Be conservative with very high scores. Use high scores only when you think "
            "speaking now would materially help."
            % {"name": peer["name"], "task": mapping["task_description"],
               "advice": mapping["advice"], "candidate": mapping["candidate_answer"],
               "role": mapping["role_description"], "public": mapping["public_context"],
               "private": mapping["private_memory"], "spoken": mapping["own_speak_history"],
               "label": turn_label, "round": round_id, "turn": turn_idx})

    def _approve_prompt(self, peer, problem, advice, candidate, approval_round) -> str:
        mapping = self._peer_mapping(peer, problem, advice, candidate, "approval",
                                     "", "Approval round %d" % approval_round)
        return (
            "You are %(name)s, one peer in a small math deliberation group.\n\n"
            "Problem:\n%(task)s\n\n"
            "Current candidate answer:\n%(candidate)s\n\n"
            "Outer-loop feedback:\n%(advice)s\n\n"
            "Your reasoning style:\n%(role)s\n\n"
            "Public discussion context:\n%(public)s\n\n"
            "Your deferred private notes:\n%(private)s\n\n"
            "Your own speaking history:\n%(spoken)s\n\n"
            "Current turn label:\nApproval round %(ar)d\n\n"
            "Current approval round: %(ar)d\n\n"
            "If you think the candidate is incomplete, imprecise, or wrong, try to correct it.\n"
            "Your review will be shared with all peers in this review turn.\n\n"
            "Return a JSON object with exactly these keys:\n"
            '- "approve": true if you accept the candidate answer as the current MAS answer, '
            'otherwise false\n'
            '- "feedback": a short review\n'
            '- "revised_answer": a boxed answer like \\boxed{...} if you think the candidate '
            'should be replaced or completed, otherwise empty string\n\n'
            "All agents, including the one who originally proposed the candidate answer, "
            "must participate in this approval discussion."
            % {"name": peer["name"], "task": mapping["task_description"],
               "candidate": mapping["candidate_answer"], "advice": mapping["advice"],
               "role": mapping["role_description"], "public": mapping["public_context"],
               "private": mapping["private_memory"], "spoken": mapping["own_speak_history"],
               "ar": approval_round})

    def _parse_poll(self, text):
        data = extract_json_object(text, ["score", "reason", "intent",
                                          "candidate_answer", "has_candidate_answer"])
        score = data.get("score", extract_int_field(text, "score", 1))
        try:
            score = int(score)
        except Exception:
            score = 1
        score = max(1, min(score, 100))
        intent = str(data.get("intent", "") or "").strip()
        reason = str(data.get("reason", "") or "").strip()
        candidate = normalize_boxed(str(data.get("candidate_answer", "") or "").strip())
        if not intent and not data:
            intent = text.strip()
        if not candidate:
            candidate = (extract_labeled_boxed(intent or text,
                         ["candidate_answer", "candidate answer", "final_answer", "final answer"])
                         or normalize_boxed(intent or text))
        return {"score": score, "reason": reason, "intent": intent,
                "candidate_answer": candidate, "parse_succeeded": bool(data)}

    def _parse_approval(self, text):
        data = extract_json_object(text, ["approve", "feedback", "revised_answer"])
        revised = normalize_boxed(str(data.get("revised_answer", "") or "").strip())
        approve = coerce_bool_value(data.get("approve"), default=False)
        if not data:
            from .parsing import extract_bool_field
            approve = extract_bool_field(text, "approve", default=False)
        feedback = str(data.get("feedback", "") or "").strip() or text
        if not revised:
            revised = extract_labeled_boxed(
                text, ["revised_answer", "revised answer", "suggested revision"])
        return {"approve": approve, "feedback": feedback, "revised_answer": revised,
                "parse_succeeded": bool(data)}

    def _approval_reached(self, approvals) -> bool:
        """Port of ``_approval_reached`` (broadcast_deliberation.py:741-746)."""
        if not approvals:
            return False
        if self.approval_policy == "majority":
            return sum(1 for item in approvals if item) > (len(approvals) // 2)
        return all(approvals)

    def _choose_candidate(self, current_candidate, revisions) -> str:
        """Port of ``_choose_candidate`` (broadcast_deliberation.py:769-779)."""
        clean = [normalize_boxed(item) for item in revisions if normalize_boxed(item)]
        if not clean:
            return current_candidate
        if self.candidate_selection_policy == "latest_revision":
            return clean[-1]
        if self.candidate_selection_policy == "first_revision":
            return clean[0]
        from collections import Counter
        return Counter(clean).most_common(1)[0][0]

    def _approval_loop(self, problem, advice, candidate, round_id, events):
        current_candidate = normalize_boxed(candidate)
        consensus = False
        for approval_round in range(self.approval_rounds):
            approvals, revisions = [], []
            for peer in self.peers:
                text = self._peer_call(
                    peer, self._approve_prompt(peer, problem, advice,
                                               current_candidate, approval_round),
                    events, "approval_%d" % approval_round)
                parsed = self._parse_approval(text)
                approvals.append(bool(parsed["approve"]))
                if parsed["revised_answer"]:
                    revisions.append(parsed["revised_answer"])
                position = ("approve" if parsed["approve"]
                            else ("revise" if parsed["revised_answer"] else "reject"))
                self.candidate_revision_memory.add(
                    stage="approval_%d" % approval_round, source=peer["name"],
                    action=position,
                    candidate_answer=(parsed["revised_answer"] or current_candidate),
                    rationale_or_review=parsed["feedback"])
                shared = ("Source Type: peer review/suggestion (not evaluator feedback; "
                          "not system proof)\nCandidate under review: %s\n"
                          "Review Position: %s\nPeer Review: %s"
                          % (current_candidate or "[None]", position,
                             parsed["feedback"] or "[no substantive feedback]"))
                if parsed["revised_answer"]:
                    shared += ("\nProposed Correction (peer suggestion; verify "
                               "independently): %s" % parsed["revised_answer"])
                self.public_history.append("%s: %s" % (peer["name"], shared))
                self.speak_history.setdefault(peer["name"], []).append(shared)

            if self._approval_reached(approvals):
                consensus = True
                break
            updated = self._choose_candidate(current_candidate, revisions)
            if updated and updated != current_candidate:
                events.append({"type": "summary",
                               "stage": "approval_%d_candidate_update" % approval_round,
                               "role": "system", "sender": "system",
                               "content": "Candidate updated from %s to %s"
                                          % (current_candidate or "[None]", updated)})
                self.public_history.append(
                    "system: Candidate updated from %s to %s"
                    % (current_candidate or "[None]", updated))
                current_candidate = updated
        return consensus, current_candidate

    def _format_final_output(self, candidate, consensus_reached, candidate_source) -> str:
        """Port of ``_format_final_output`` (broadcast_deliberation.py:781-799)."""
        boxed = normalize_boxed(candidate) or "\\boxed{}"
        return ("Broadcast-Deliberation Final Output\n"
                "Consensus Status: %s\n"
                "Candidate Source: %s\n"
                "Final Answer For Evaluator:\n%s"
                % ("consensus_reached" if consensus_reached else "consensus_not_reached",
                   candidate_source or "unknown", boxed))

    def step(self, problem, advice, previous_plan, round_id, events, dry_run=False):
        if dry_run:
            peer = self.peers[0] if self.peers else {"name": "Peer", "role_description": ""}
            events.append({"type": "dry_run_prompt", "stage": "poll_0",
                           "role": "deliberator",
                           "prompt": self._poll_prompt(peer, problem, advice, "",
                                                       "Outer round 0, discussion turn 0",
                                                       0, 0)})
            role_spec = self.prompts_for("deliberator")
            mapping = self._peer_mapping(peer, problem, advice, "", "discussion",
                                         self.discussion_instruction,
                                         "Outer round 0, discussion turn 0")
            events.append({"type": "dry_run_prompt", "stage": "discussion_0",
                           "role": "deliberator",
                           "prompt": (_render(role_spec.get("prepend_prompt", ""), mapping)
                                      + "\n\n"
                                      + _render(role_spec.get("append_prompt", ""), mapping)).strip()})
            events.append({"type": "dry_run_prompt", "stage": "approval_0",
                           "role": "deliberator",
                           "prompt": self._approve_prompt(peer, problem, advice, "", 0)})
            return "", "", "", False, None

        current_candidate = normalize_boxed(previous_plan)
        candidate_source = "previous_attempt" if current_candidate else ""
        consensus_reached = False

        for turn_idx in range(self.discussion_rounds):
            turn_label = "Outer round %d, discussion turn %d" % (round_id, turn_idx)
            polls = []
            for peer in self.peers:
                text = self._peer_call(
                    peer, self._poll_prompt(peer, problem, advice, current_candidate,
                                            turn_label, round_id, turn_idx),
                    events, "poll_%d" % turn_idx)
                polls.append(self._parse_poll(text))

            best_idx, best_score = 0, -1
            for idx, poll in enumerate(polls):
                if poll["score"] > best_score:
                    best_idx, best_score = idx, poll["score"]

            # Peers at or above the threshold that did NOT win defer a note.
            for idx, (peer, poll) in enumerate(zip(self.peers, polls)):
                if idx == best_idx or poll["score"] < self.speak_threshold:
                    continue
                if not (is_meaningful_public_text(poll["reason"])
                        or is_meaningful_public_text(poll["intent"])
                        or poll["candidate_answer"]):
                    continue
                note = ("Deferred note from discussion turn %d.\nReason to speak: %s\n"
                        "Intended contribution: %s"
                        % (turn_idx, poll["reason"], poll["intent"]))
                self.private_notes.setdefault(peer["name"], []).append(note)
                events.append({"type": "summary", "stage": "deferred_%d" % turn_idx,
                               "role": "deliberator", "sender": peer["name"],
                               "content": note})

            speaker = self.peers[best_idx]
            role_spec = self.prompts_for("deliberator")
            mapping = self._peer_mapping(speaker, problem, advice, current_candidate,
                                         "discussion", self.discussion_instruction,
                                         turn_label)
            speech = self._peer_call(
                speaker,
                (_render(role_spec.get("prepend_prompt", ""), mapping) + "\n\n"
                 + _render(role_spec.get("append_prompt", ""), mapping)).strip(),
                events, "discussion_%d" % turn_idx)

            if is_meaningful_public_text(speech):
                self.public_history.append("%s: %s" % (speaker["name"], speech))
                self.speak_history.setdefault(speaker["name"], []).append(speech)
                spoken_candidate = normalize_boxed(extract_boxed(speech))
            else:
                spoken_candidate = ""

            poll_candidate = polls[best_idx]["candidate_answer"]
            if not poll_candidate:
                best_poll_score = -1
                for peer, poll in zip(self.peers, polls):
                    if poll["candidate_answer"] and poll["score"] > best_poll_score:
                        poll_candidate = poll["candidate_answer"]
                        best_poll_score = poll["score"]
            proposed = spoken_candidate or poll_candidate

            if proposed:
                current_candidate = proposed
                candidate_source = speaker["name"]
                self.candidate_revision_memory.add(
                    stage="candidate_review_%d" % turn_idx, source=candidate_source,
                    action="select_for_review", candidate_answer=current_candidate,
                    rationale_or_review="Candidate promoted during discussion turn %d." % turn_idx)
                self.public_history.append(
                    "system: Candidate answer under group review:\nSource: %s\n%s"
                    % (candidate_source, current_candidate))
                consensus_reached, current_candidate = self._approval_loop(
                    problem, advice, current_candidate, round_id, events)
                if consensus_reached:
                    break

        if not current_candidate:
            # Final proposal round: every peer proposes, highest confidence wins.
            best_conf, best_answer, best_name = -1, "", ""
            for peer in self.peers:
                prompt = (self._poll_prompt(peer, problem, advice, "",
                                            "Final proposal round", round_id,
                                            self.discussion_rounds)
                          + "\n\nThis is the FINAL PROPOSAL round. You must propose your "
                            "best final answer now in candidate_answer.")
                parsed = self._parse_poll(
                    self._peer_call(peer, prompt, events, "final_proposal"))
                if parsed["candidate_answer"] and parsed["score"] > best_conf:
                    best_conf = parsed["score"]
                    best_answer = parsed["candidate_answer"]
                    best_name = peer["name"]
            current_candidate = best_answer
            candidate_source = best_name or "final_proposal"

        final_output = self._format_final_output(current_candidate, consensus_reached,
                                                 candidate_source)
        evaluation = self.run_evaluation(problem, final_output, events, "evaluation",
                                         current_reasoning=self._public_context())
        feedback = self.feedback_text(evaluation)

        if not evaluation.passed:
            self.failed_attempt_memory.add(
                submitted_answer=(evaluation.final_answer or current_candidate),
                evaluator_signal="FAIL", evaluator_hint=feedback,
                repair_summary="Peers should revise the rejected candidate.",
                source_stage="evaluation")

        return final_output, feedback, current_candidate, evaluation.passed, evaluation

    def run(self, problem, dry_run=False):
        # Shared-channel state is per-problem, like the upstream env.reset().
        self.public_history = []
        self.private_notes = {}
        self.speak_history = {}
        return super(BroadcastProtocol, self).run(problem, dry_run=dry_run)


PROTOCOL_CLASSES = {
    "baseline": BaselineProtocol,
    "single": SingleAgentProtocol,
    "per": PerProtocol,
    "broadcast": BroadcastProtocol,
}


def build_protocol(spec, clients, evaluator, logger=None):
    protocol_id = str(spec.get("protocol_id", "")).strip()
    if protocol_id not in PROTOCOL_CLASSES:
        raise ValueError("Unknown protocol_id %r; expected one of %s"
                         % (protocol_id, sorted(PROTOCOL_CLASSES)))
    return PROTOCOL_CLASSES[protocol_id](spec, clients, evaluator, logger=logger)

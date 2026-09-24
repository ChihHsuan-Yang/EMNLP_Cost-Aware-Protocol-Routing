"""Deterministic offline provider. No network, no cost, no API key.

Purpose: let an external auditor exercise the complete four-protocol pipeline
-- every role, both evaluator calls, routing, approval voting, the outer retry
loop, and all run artifacts -- without an endpoint.

What it is NOT: a model. It does not solve anything. It replies with
syntactically valid, format-conformant text whose CONTENT is scripted from a
hash of the prompt, so runs are byte-reproducible. Accuracy numbers from a mock
run are meaningless by construction; only the plumbing is being tested.

Determinism contract: output depends only on (seed, model, messages). The same
command run twice produces byte-identical predictions. Token counts are a
deterministic whitespace-based estimate, not a tokenizer.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from .client import BaseProvider


def _digest(seed: int, model: str, messages: List[Dict[str, str]]) -> int:
    hasher = hashlib.sha256()
    hasher.update(str(seed).encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update(str(model).encode("utf-8"))
    for message in messages:
        hasher.update(b"\x00")
        hasher.update(str(message.get("role", "")).encode("utf-8"))
        hasher.update(b"\x01")
        hasher.update(str(message.get("content", "")).encode("utf-8"))
    return int.from_bytes(hasher.digest()[:8], "big")


def _estimate_tokens(text: str) -> int:
    """Whitespace-and-punctuation estimate. NOT a real tokenizer."""
    if not text:
        return 0
    return max(1, len(re.findall(r"\w+|[^\w\s]", str(text))))


class MockProvider(BaseProvider):
    """Scripted, deterministic stand-in for an OpenAI-compatible endpoint.

    Role detection is by prompt content, because the runner sends role-specific
    prompt templates. ``answer_mode`` controls what the fake solver emits:

      * ``hash``   -- a hash-derived integer. Almost always "wrong"; exercises
                      the FAIL -> hint -> repair -> re-evaluate paths.
      * ``gold``   -- echo the gold answer when the runner supplies it, so the
                      PASS path and early stopping are exercised.
      * ``mixed``  -- gold for a deterministic subset (``gold_rate``), hash
                      otherwise. Default: exercises both branches in one run.

    The mock judge is a STRING COMPARISON against the gold answer, not a model.
    It emits the exact ``Correctness:``/``Response:`` format the real parser
    requires, so the parsing path under test is the real one.
    """

    name = "mock"

    def __init__(self, seed=0, answer_mode="mixed", gold_rate=0.5,
                 fail_rate=0.0, malformed_rate=0.0):
        self.seed = int(seed)
        self.answer_mode = str(answer_mode)
        self.gold_rate = float(gold_rate)
        self.fail_rate = float(fail_rate)
        self.malformed_rate = float(malformed_rate)
        # SIDE-CHANNEL gold registry: problem_text -> gold answer.
        # The runner populates this directly, out of band. Gold is therefore
        # NEVER written into any prompt -- not the solver's, not the judge's.
        # A real provider has no such channel and cannot be given one, so this
        # cannot leak into a real run.
        self._gold_by_problem = []

    def register_gold(self, problem_text: str, gold_answer: str) -> None:
        """Teach the mock the gold answer for one problem, out of band."""
        key = " ".join(str(problem_text or "").split())[:400]
        if key:
            self._gold_by_problem.append((key, str(gold_answer or "")))

    def describe(self) -> Dict[str, Any]:
        return {
            "provider_type": self.name,
            "seed": self.seed,
            "answer_mode": self.answer_mode,
            "gold_rate": self.gold_rate,
            "fail_rate": self.fail_rate,
            "malformed_rate": self.malformed_rate,
            "network": False,
            "gold_registry_size": len(self._gold_by_problem),
            "gold_channel": ("out-of-band registry; gold is never written into "
                             "any prompt, actor or judge"),
            "warning": (
                "MOCK BACKEND. Responses are scripted from a prompt hash. "
                "No model was queried. Accuracy from this run is meaningless."
            ),
        }

    # -- role detection ---------------------------------------------------

    @staticmethod
    def _joined(messages) -> str:
        return "\n".join(str(m.get("content", "")) for m in messages)

    def _role_of(self, text: str) -> str:
        if "You are the Evaluator" in text or "Correctness: 0 or 1" in text:
            return "judge"
        if "You are the Planner" in text:
            return "planner"
        if "You are the Executor" in text:
            return "executor"
        if "You are the Reviewer" in text:
            return "reviewer"
        if "mandatory turn-allocation poll" in text:
            return "poll"
        if '"approve"' in text and '"revised_answer"' in text:
            return "approve"
        if "one peer in a" in text:
            return "deliberate"
        return "solver"

    # -- gold plumbing ----------------------------------------------------

    def _gold_for_prompt(self, text: str) -> str:
        """Look the gold answer up from the side-channel registry.

        Matches by locating a registered problem statement inside the prompt.
        Returns "" when the problem is unknown, in which case the mock simply
        produces hash answers and everything FAILs -- still a valid exercise
        of the pipeline, just without the PASS path.
        """
        haystack = " ".join(str(text or "").split())
        best = ""
        best_len = 0
        for key, gold in self._gold_by_problem:
            if len(key) > best_len and key in haystack:
                best, best_len = gold, len(key)
        return best

    @staticmethod
    def _candidate_from_prompt(text: str) -> str:
        from .parsing import extract_boxed
        return extract_boxed(text)

    def _solver_answer(self, digest: int, gold: str) -> str:
        if self.answer_mode == "gold" and gold:
            return gold
        if self.answer_mode == "mixed" and gold:
            if (digest % 1000) / 1000.0 < self.gold_rate:
                return gold
        return str(digest % 9973)

    # -- scripted bodies --------------------------------------------------

    def _body(self, role, digest, text) -> str:
        gold = self._gold_for_prompt(text)
        nonce = digest % 100000

        if role == "judge":
            candidate = self._candidate_from_prompt(text)
            gold_norm = " ".join(gold.split()).strip().lower()
            cand_norm = " ".join(candidate.split()).strip().lower()
            passed = bool(gold_norm) and gold_norm == cand_norm
            if passed:
                return ("Verdict: PASS\nCorrectness: 1\n"
                        "Response: Mock judge: candidate string-matches the reference.")
            return ("Verdict: FAIL\nCorrectness: 0\n"
                    "Response: Mock judge: candidate does not string-match the "
                    "reference; check the answer shape and completeness.")

        if role == "poll":
            score = 10 + (digest % 90)
            return ('{"score": %d, "reason": "mock poll %d", '
                    '"intent": "contribute a mock point", '
                    '"candidate_answer": "\\\\boxed{%s}", '
                    '"has_candidate_answer": true}'
                    % (score, nonce, self._solver_answer(digest, gold)))

        if role == "approve":
            approve = (digest % 3) != 0
            if approve:
                return ('{"approve": true, "feedback": "Mock peer accepts the candidate.", '
                        '"revised_answer": ""}')
            return ('{"approve": false, "feedback": "Mock peer objects on completeness.", '
                    '"revised_answer": "\\\\boxed{%s}"}'
                    % self._solver_answer(digest, gold))

        if role == "planner":
            return ("DELTA:\n- mock update %d\n- restate the givens\n"
                    "1) Givens: as stated in the problem.\n"
                    "2) Target quantity and answer form: a single value.\n"
                    "3) Key lemmas: mock lemma.\n"
                    "4) Ordered execution steps: compute, then box." % nonce)

        if role == "reviewer":
            if (digest % 4) == 0:
                return ("Diagnosis:\n- Mock reviewer is satisfied.\n"
                        "Fix Instruction:\n- None.\n"
                        "Final Answer For Evaluator:\n\\boxed{%s}\n[Agree]"
                        % self._solver_answer(digest, gold))
            target = "Executor" if (digest % 2) == 0 else "Planner"
            return ("Diagnosis:\n- Mock reviewer wants a check (%d).\n"
                    "Fix Instruction:\n- Recompute the final step.\n"
                    "[Route:%s]" % (nonce, target))

        answer = self._solver_answer(digest, gold)
        if self.malformed_rate > 0 and (digest % 997) / 997.0 < self.malformed_rate:
            return "Mock response %d with no boxed final answer at all." % nonce
        return ("Mock reasoning for stage '%s' (nonce %d).\n"
                "Step 1: restate.\nStep 2: compute.\n"
                "Final Answer: %s\n\\boxed{%s}" % (role, nonce, answer, answer))

    # -- provider interface -----------------------------------------------

    def chat(self, messages, model, temperature, max_tokens, timeout_seconds):
        text = self._joined(messages)
        digest = _digest(self.seed, model, messages)
        role = self._role_of(text)

        if self.fail_rate > 0 and (digest % 991) / 991.0 < self.fail_rate:
            raise ConnectionError("mock injected transient failure")

        content = self._body(role, digest, text)
        prompt_tokens = _estimate_tokens(text)
        completion_tokens = min(int(max_tokens), _estimate_tokens(content))
        return {
            "id": "mock-%016x" % digest,
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

#!/usr/bin/env python3
"""Regression tests for behaviours whose loss would change the science.

Run:  python3 tests/test_fidelity.py
No pytest required.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from protocol_routing_exec import parsing as P            # noqa: E402
from protocol_routing_exec.evaluator import LlmEvaluator  # noqa: E402
from protocol_routing_exec.mock_backend import MockProvider  # noqa: E402
from protocol_routing_exec.client import ChatClient, TokenLedger  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


print("\n[1] extract_boxed returns the LAST well-formed box, brace-balanced")
check("nested braces survive",
      P.extract_boxed(r"\boxed{\frac{1}{2}}") == r"\frac{1}{2}")
check("last box wins",
      P.extract_boxed(r"\boxed{1} then \boxed{2}") == "2")
check("unterminated box skipped, earlier one returned",
      P.extract_boxed(r"\boxed{7} and \boxed{oops") == "7")
check("no box -> empty", P.extract_boxed("no answer here") == "")

print("\n[2] mgsm-evaluator reads Correctness ONLY; Verdict is never parsed")
ok, advice = P.parse_mgsm_evaluator("Verdict: PASS\nCorrectness: 0\nResponse: r")
check("Correctness 0 beats a contradicting Verdict: PASS", ok is False,
      "-> got %r" % ok)
ok, _ = P.parse_mgsm_evaluator("Verdict: FAIL\nCorrectness: 1\nResponse: r")
check("Correctness 1 beats a contradicting Verdict: FAIL", ok is True)
try:
    P.parse_mgsm_evaluator("Verdict: PASS\nResponse: no correctness line")
    check("missing Correctness raises", False)
except P.OutputParserError:
    check("missing Correctness raises OutputParserError", True)
ok, _ = P.parse_mgsm_evaluator("Correctness: 10\nResponse: r")
check("single-digit regex makes 'Correctness: 10' parse as 1 (upstream quirk)",
      ok is True)

print("\n[3] route parsing: last tag wins, unparseable -> ''")
check("[Agree]", P.parse_route("blah\n[Agree]") == "agree")
check("[Route:Planner]", P.parse_route("x\n[Route:Planner]") == "planner")
check("last tag wins", P.parse_route("[Agree] ... [Route:Executor]") == "executor")
check("no tag -> empty", P.parse_route("no tag at all") == "")

print("\n[4] box gate: no boxed answer means the judge is NEVER called")
ledger = TokenLedger()
provider = MockProvider(seed=0)
client = ChatClient(provider, "m", 0.0, 256, 10.0, 2, 1.0, ledger)
ev = LlmEvaluator(client, "Judge ${solution} vs ${result}", "Correctness: 0 or 1")
result = ev.evaluate("problem", "I have no boxed answer.", "42")
check("verdict is FAIL", result.passed is False)
check("direct_protocol_fail set", result.direct_protocol_fail is True)
check("reason is missing_boxed_final_answer",
      result.direct_protocol_fail_reason == "missing_boxed_final_answer")
check("ZERO judge calls billed", result.judge_calls == 0)
check("ZERO tokens billed", ledger.snapshot()["calls"] == 0)

print("\n[5] judge call count: 1 on PASS, 1 on FAIL without hints, 2 with hints")
provider = MockProvider(seed=0)
provider.register_gold("problem text", "42")
ledger = TokenLedger()
client = ChatClient(provider, "m", 0.0, 256, 10.0, 2, 1.0, ledger)
ev = LlmEvaluator(client, "You are the Evaluator. ${task_description} ${solution} ${result}",
                  "Correctness: 0 or 1")
r_pass = ev.evaluate("problem text", r"\boxed{42}", "42")
check("PASS makes one judge call", r_pass.passed and r_pass.judge_calls == 1,
      "-> passed=%s calls=%d" % (r_pass.passed, r_pass.judge_calls))
r_fail_hint = ev.evaluate("problem text", r"\boxed{99}", "42",
                          include_hint_on_fail=True)
check("FAIL with hints makes TWO judge calls",
      (not r_fail_hint.passed) and r_fail_hint.judge_calls == 2,
      "-> calls=%d" % r_fail_hint.judge_calls)
r_fail_plain = ev.evaluate("problem text", r"\boxed{99}", "42",
                           include_hint_on_fail=False)
check("FAIL without hints (baseline) makes ONE judge call",
      (not r_fail_plain.passed) and r_fail_plain.judge_calls == 1,
      "-> calls=%d" % r_fail_plain.judge_calls)
check("baseline path produces no hint text", r_fail_plain.hint_advice == "")

print("\n[6] unparseable judge is scored 0 == wrong answer, but flagged")


class AlwaysGarbage(MockProvider):
    def chat(self, messages, model, temperature, max_tokens, timeout_seconds):
        return {"choices": [{"message": {"content": "I refuse to follow the format."},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


ev_bad = LlmEvaluator(ChatClient(AlwaysGarbage(), "m", 0.0, 256, 10.0, 1, 1.0,
                                 TokenLedger()),
                      "${solution}", "x", max_parse_retry=3)
r_bad = ev_bad.evaluate("p", r"\boxed{1}", "1")
check("scored FAIL like upstream", r_bad.passed is False)
check("but flagged judge_unparseable (upstream does NOT flag this)",
      r_bad.judge_unparseable is True)

print("\n[7] reviewer_feedback_mode 'plain' DISCARDS the judge's advice text")
from protocol_routing_exec.evaluator import format_reviewer_feedback  # noqa: E402
plain = format_reviewer_feedback("llm", False, "the real diagnostic hint", "plain")
hint = format_reviewer_feedback("llm", False, "the real diagnostic hint", "hint")
check("plain drops the advice", "the real diagnostic hint" not in plain)
check("hint keeps the advice", "the real diagnostic hint" in hint)

print("\n[8] dataset loaders disagree on answer priority, deliberately")
from protocol_routing_exec.datasets import (  # noqa: E402
    _normalize_generic_jsonl, _normalize_omni_math)
row = {"question": "q", "input": "q", "answer": "None", "answer_number": "7"}
check("omni-math prefers answer_number",
      _normalize_omni_math(row, 0)["answer"] == "7")
row2 = {"input": "q", "answer": "A", "answer_number": "0"}
check("jsonl prefers answer",
      _normalize_generic_jsonl(row2, 0)["answer"] == "A")

print("\n[9] Template.safe_substitute collapses $$ -> $ (UPSTREAM behaviour)")
from string import Template  # noqa: E402
rendered = Template("keep `$` and `$$` here").safe_substitute({"x": "y"})
check("$$ becomes $ exactly as agentverse/agents/base.py:121 does",
      rendered == "keep `$` and `$` here", "-> %r" % rendered)

print("\n[10] no secret-shaped value can reach an artifact")
from protocol_routing_exec.artifacts import scrub_secrets  # noqa: E402
check("api_key caught", scrub_secrets({"a": {"api_key": "sk-x"}}) == ["a.api_key"])
check("base_url caught", scrub_secrets({"base_url": "https://h/v1"}) == ["base_url"])
check("env var NAMES are fine",
      scrub_secrets({"api_key_env": "INFERENCE_API_KEY"}) == [])

print("\n" + "=" * 60)
if FAILURES:
    print("FAILED: %d check(s): %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("ALL FIDELITY CHECKS PASSED")
sys.exit(0)

"""Answer extraction and output parsing.

Every function here is a direct port of the corresponding routine in the
original research engine. The source file and function are named in each
docstring so a reader can diff them against the upstream repository.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


class OutputParserError(ValueError):
    """Raised when a model response does not match the required format.

    Upstream equivalent: agentverse/output_parser/output_parser.py OutputParserError.
    """


def extract_boxed(text: str) -> str:
    """Return the LAST well-formed ``\\boxed{...}`` payload in ``text``.

    Exact port of agentverse/evaluation/common.py::extract_boxed (lines 8-40).
    Brace-balanced, so nested braces survive; an unterminated ``\\boxed{`` is
    skipped rather than returned truncated. Returns "" when none is found.
    """
    if not text:
        return ""
    raw = str(text)
    marker = r"\boxed{"
    last_match = ""
    start = 0

    while True:
        idx = raw.find(marker, start)
        if idx == -1:
            break

        cursor = idx + len(marker)
        depth = 1
        chunks: List[str] = []

        while cursor < len(raw) and depth > 0:
            char = raw[cursor]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            chunks.append(char)
            cursor += 1

        if depth == 0:
            last_match = "".join(chunks).strip()
        start = idx + 1

    return last_match


def extract_final_answer(text: str) -> str:
    """Boxed answer if present, else the last non-empty line.

    Exact port of agentverse/evaluation/common.py::extract_final_answer (43-55).

    NOTE the silent fallback: when there is no boxed answer this returns the
    last non-empty line with a trailing "." stripped. In the original engine
    this fallback is only reached AFTER the box_required gate in the evaluator
    has already passed, so in practice it operates on boxed text.
    """
    if not text:
        return ""

    boxed = extract_boxed(text)
    if boxed:
        return boxed

    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return str(text).strip()

    return lines[-1].rstrip(".")


def normalize_boxed(text: str) -> str:
    """Render a candidate as exactly ``\\boxed{...}`` or "" when absent.

    Port of the ``_normalize_boxed`` helper used by the broadcast rule
    (agentverse/environments/tasksolving_env/rules/broadcast_deliberation.py).
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    inner = extract_boxed(raw)
    if inner:
        return "\\boxed{%s}" % inner
    return ""


def boxed_only(candidate_text: str) -> str:
    """``\\boxed{x}`` or the literal marker string when no box is present."""
    boxed = extract_boxed(candidate_text or "")
    return "\\boxed{%s}" % boxed if boxed else "[No boxed answer]"


def submitted_final_answer_for_trace(text: str) -> str:
    """Trace-line rendering of what was actually handed to the evaluator."""
    boxed = extract_boxed(text or "")
    return "\\boxed{%s}" % boxed if boxed else "[No extracted final answer]"


# ---------------------------------------------------------------------------
# Evaluator verdict parsing
# ---------------------------------------------------------------------------

def parse_mgsm_evaluator(
    text: str,
    dimensions: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Parse the judge response into (passed, advice).

    Exact port of the ``mgsm-evaluator`` parser,
    agentverse/output_parser/output_parser.py::MGSMEvaluatorParser.parse
    (lines 515-546), with ``dimensions: [Correctness]`` as used by all four
    paper configs.

    Two behaviours of the original that are faithfully preserved because they
    affect the scientific result:

    1. ``Verdict: PASS/FAIL`` is NEVER READ. The prompts ask the judge for a
       Verdict line, but the runtime parser only matches ``Correctness:\\s*(\\d)``.
       The Verdict line is consumed only by offline analysis code, and only as
       a fallback when Correctness is missing.
    2. The score pattern is a SINGLE digit ``(\\d)``, so "Correctness: 10"
       parses as 1 (True). A parsed value other than 0 or 1 raises.

    Raises OutputParserError when Correctness or Response cannot be found; the
    caller is expected to retry (see client.max_retry) and, on exhaustion, to
    record score 0 == FAIL.
    """
    dimensions = dimensions or ["Correctness"]
    cleaned_output = re.sub(r"\n+", "\n", str(text or "").strip())

    patterns = [
        re.compile(r"(?:\d.\s*)?" + dimension + r":\s*(\d)")
        for dimension in dimensions
    ]
    try:
        score_num = [int(pattern.findall(cleaned_output)[0]) for pattern in patterns][0]
        if score_num == 0:
            score = False
        elif score_num == 1:
            score = True
        else:
            raise ValueError("Bad score!")
        pat = re.compile(r"(?:\d.\s*)?Response:\s*(.+)", re.DOTALL)
        advice = pat.findall(cleaned_output)[0]
    except (IndexError, ValueError):
        raise OutputParserError(str(text))
    return score, advice


def coerce_evaluator_score(score: Any) -> bool:
    """Coerce a parsed evaluator score to a boolean PASS/FAIL.

    Port of ``_coerce_evaluator_score``. In the original engine this exact
    function body appears in FOUR modules (rules/per.py:217, rules/
    broadcast_deliberation.py:41, rules/diverse_hypothesis.py:60, and as
    ``_coerce_score_to_bool`` in rules/evaluator/per.py:47). Here it exists
    once. The ``>= 8`` branch is dead for the paper protocols because the
    mgsm-evaluator parser returns a bool, which is matched first.
    """
    if isinstance(score, bool):
        return score
    if isinstance(score, int):
        return score == 1 or score >= 8
    if isinstance(score, (list, tuple)):
        return bool(score) and all(coerce_evaluator_score(item) for item in score)
    return bool(score)


# ---------------------------------------------------------------------------
# PER reviewer route parsing
# ---------------------------------------------------------------------------

_ROUTE_PATTERNS = (
    ("agree", re.compile(r"\[Agree\]", re.IGNORECASE)),
    ("planner", re.compile(r"\[Route:\s*Planner\]", re.IGNORECASE)),
    ("executor", re.compile(r"\[Route:\s*Executor\]", re.IGNORECASE)),
    ("evaluate", re.compile(r"\[Route:\s*Evaluat(?:e|or)\]", re.IGNORECASE)),
)

_EXECUTOR_FAIL_MARKERS = (
    "boxed answer", "boxed", "format", "latex", "markup", "unit",
    "token", "raw numeric", "presentation", "output", "missing",
)


def parse_route(review_text: str) -> str:
    """Return one of {"agree","planner","executor","evaluate",""}.

    Mirrors ``_parse_route`` in rules/per.py. The ``mgsm-critic-route`` parser
    upstream deliberately keeps the reviewer's FULL text so the rule layer can
    regex the tag out of it; that division is preserved here.

    The LAST tag occurring in the text wins, matching the upstream contract
    that the route tag must be the final line.
    """
    text = str(review_text or "")
    best_name = ""
    best_pos = -1
    for name, pattern in _ROUTE_PATTERNS:
        for match in pattern.finditer(text):
            if match.start() > best_pos:
                best_pos = match.start()
                best_name = name
    return best_name


def default_fail_route(eval_advice: str, review_text: str = "") -> str:
    """Pick a forced route after an evaluator FAIL.

    Exact port of ``_default_fail_route`` (rules/per.py:252-269): keyword
    match against a fixed marker list decides Executor, else Planner.
    """
    combined = ("%s\n%s" % (eval_advice, review_text)).lower()
    if any(marker in combined for marker in _EXECUTOR_FAIL_MARKERS):
        return "[Route:Executor]"
    return "[Route:Planner]"


def extract_reviewer_submission_candidate(review_text: str) -> str:
    """Pull the reviewer's ``Final Answer For Evaluator:`` block, if present."""
    text = str(review_text or "")
    marker = re.search(r"Final Answer For Evaluator\s*:", text, flags=re.IGNORECASE)
    if marker:
        tail = text[marker.end():]
        boxed = extract_boxed(tail)
        if boxed:
            return "\\boxed{%s}" % boxed
    return ""


# ---------------------------------------------------------------------------
# Broadcast JSON field parsing
# ---------------------------------------------------------------------------

def extract_json_object(
    text: str,
    expected_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Best-effort recovery of one JSON object from a model response.

    Port of ``_extract_json_object`` in
    agentverse/agents/tasksolving_agent/deliberator.py. Returns {} when nothing
    usable is found; callers treat {} as "parse failed" and fall back to
    regex field extraction, exactly as upstream does.
    """
    raw = str(text or "").strip()
    if not raw:
        return {}

    fenced = re.search(r"```(?:json)?\s*(.+?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(raw)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # Fall back to brace scanning, preferring objects that carry expected keys.
    best: Dict[str, Any] = {}
    for start in (m.start() for m in re.finditer(r"\{", raw)):
        depth = 0
        for pos in range(start, len(raw)):
            if raw[pos] == "{":
                depth += 1
            elif raw[pos] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(raw[start:pos + 1])
                    except Exception:
                        break
                    if not isinstance(parsed, dict):
                        break
                    if expected_keys and any(k in parsed for k in expected_keys):
                        return parsed
                    if not best:
                        best = parsed
                    break
    return best


def coerce_bool_value(value: Any, default: bool = False) -> bool:
    """Port of ``_coerce_bool_value`` (deliberator.py)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "approve", "approved"}:
            return True
        if lowered in {"false", "no", "n", "0", "reject", "rejected"}:
            return False
    return default


def extract_int_field(text: str, field: str, default: int = 1) -> int:
    """Regex fallback for an integer field when JSON parsing failed."""
    match = re.search(r'"?%s"?\s*[:=]\s*(-?\d+)' % re.escape(field), str(text or ""),
                      flags=re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return default
    return default


def extract_bool_field(text: str, field: str, default: bool = False) -> bool:
    """Regex fallback for a boolean field when JSON parsing failed."""
    match = re.search(r'"?%s"?\s*[:=]\s*(true|false|yes|no)' % re.escape(field),
                      str(text or ""), flags=re.IGNORECASE)
    if match:
        return coerce_bool_value(match.group(1), default=default)
    return default


def extract_labeled_boxed(text: str, labels: List[str]) -> str:
    """Find a boxed answer that follows one of ``labels``."""
    raw = str(text or "")
    for label in labels:
        match = re.search(re.escape(label) + r"\s*[\"']?\s*[:=]", raw, flags=re.IGNORECASE)
        if not match:
            continue
        boxed = extract_boxed(raw[match.end():])
        if boxed:
            return "\\boxed{%s}" % boxed
    return ""


def is_meaningful_public_text(text: str) -> bool:
    """Port of ``_is_meaningful_public_text``: reject empty/placeholder speech."""
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) < 3:
        return False
    if cleaned.lower() in {"[none]", "none", "n/a", "na", "null", "[empty]", "-"}:
        return False
    return True

"""Per-question memory ledgers shared by the iterative protocols.

Port of agentverse/environments/tasksolving_env/rules/failure_memory.py. These
ledgers are question-scoped: they are created fresh for every problem and
cleared between problems, so nothing leaks across items. Neither ledger ever
contains the gold answer -- only the model's own rejected answers and the
judge's non-leaking hints.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .parsing import extract_boxed

# Verbatim from failure_memory.py:10-13. This text is prepended to the advice
# string handed to actor agents, and it materially shapes behaviour: it tells
# the model how much authority to give peer suggestions versus evaluator
# feedback. Changing it changes the protocol.
AUTHORITY_GUIDE = """Feedback Authority Guide:
- Peer or Reviewer revisions are internal suggestions. They may be useful or wrong; verify them against the task evidence and answer requirements.
- A system/protocol candidate update means the protocol selected the current candidate for further review or submission. It is not a correctness signal.
- Evaluator feedback is the external verifier signal based on evaluator-only reference material. Treat it as higher priority than peer or Reviewer suggestions, but remember it is a non-leaking hint, not the answer."""


def with_authority_guide(text: str) -> str:
    """Port of failure_memory.py::with_authority_guide (16-20)."""
    cleaned = str(text or "").strip()
    if AUTHORITY_GUIDE in cleaned:
        return cleaned
    return "\n\n".join(part for part in [AUTHORITY_GUIDE, cleaned] if part).strip()


def compact_text(text: str, max_chars: int = 320) -> str:
    """Port of failure_memory.py::_compact_text.

    Strips any ``Final Answer For Evaluator:`` block and route tags before
    truncating, so ledger entries cannot smuggle a submission directive into a
    later prompt.
    """
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(
        r"Final Answer For Evaluator:\s*.*?(?=\n\[(?:Route:Planner|Route:Executor|Agree)\]|\Z)",
        "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(
        r"\[(?:Route:Planner|Route:Executor|Route:Evaluator|Route:Evaluate|Agree)\]",
        "", cleaned)
    cleaned = " ".join(cleaned.split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars - 3].rstrip() + "..."


def normalize_candidate_answer(candidate_answer: str, fallback_text: str = "") -> str:
    """Port of failure_memory.py::_normalize_candidate_answer."""
    boxed = extract_boxed(candidate_answer or "") or extract_boxed(fallback_text or "")
    if boxed:
        return "\\boxed{%s}" % boxed
    cleaned = compact_text(candidate_answer, max_chars=240)
    return cleaned or "[No candidate answer]"


class FailedAttemptMemory(object):
    """Ring buffer of rejected evaluator submissions. Limit from config."""

    def __init__(self, limit: int = 5):
        self.limit = max(1, int(limit or 5))
        self.records: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self.records = []

    def add(self, submitted_answer, evaluator_hint, evaluator_signal="FAIL",
            repair_summary="", source_stage="evaluation") -> Dict[str, Any]:
        record = {
            "attempt_id": len(self.records) + 1,
            "submitted_answer": compact_text(submitted_answer, 180) or "[no extracted answer]",
            "evaluator_signal": str(evaluator_signal or "FAIL").strip() or "FAIL",
            "evaluator_hint": compact_text(evaluator_hint, 240) or "[no evaluator hint]",
            "repair_summary": compact_text(repair_summary, 220),
            "source_stage": str(source_stage or "evaluation").strip() or "evaluation",
        }
        self.records.append(record)
        if len(self.records) > self.limit:
            self.records = self.records[-self.limit:]
            for idx, kept in enumerate(self.records, start=1):
                kept["attempt_id"] = idx
        return record

    def update_latest_repair_summary(self, repair_summary: str) -> None:
        if not self.records:
            return
        summary = compact_text(repair_summary, 220)
        if summary:
            self.records[-1]["repair_summary"] = summary

    def render(self) -> str:
        if not self.records:
            return ("Failed Attempt Memory For This Question:\n"
                    "[No failed evaluator attempts yet.]")
        lines = [
            "Failed Attempt Memory For This Question:",
            "Use this concise ledger to avoid repeating rejected answers unless the mismatch has been fixed.",
            "Evaluator feedback is the external verifier signal; it is not the answer.",
        ]
        for record in self.records:
            details = ["signal=%s" % record["evaluator_signal"],
                       "hint=%s" % record["evaluator_hint"]]
            if record["repair_summary"]:
                details.append("fix=%s" % record["repair_summary"])
            lines.append("")
            lines.append("- A%s (%s): answer=%s"
                         % (record["attempt_id"], record["source_stage"],
                            record["submitted_answer"]))
            for detail in details:
                lines.append("  %s" % detail)
        return "\n".join(lines).strip()

    def render_for_evaluator_hint(self, max_records: int = 3) -> str:
        if not self.records:
            return "[No previous failed evaluator attempts for this question.]"
        lines = ["Previous answers summary for evaluator hint generation:"]
        for record in self.records[-max(1, int(max_records or 1)):]:
            lines.append("- Attempt %s: answer=%s"
                         % (record["attempt_id"], record["submitted_answer"]))
            lines.append("  signal=%s" % record["evaluator_signal"])
            lines.append("  hint=%s" % compact_text(record["evaluator_hint"], 160))
            if record["repair_summary"]:
                lines.append("  repair=%s" % compact_text(record["repair_summary"], 160))
        return "\n".join(lines).strip()


class CandidateRevisionMemory(object):
    """Ring buffer of candidate-answer lifecycle events (propose/review/submit)."""

    def __init__(self, limit: int = 5):
        self.limit = max(1, int(limit or 5))
        self.records: List[Dict[str, Any]] = []
        self._next_id = 1

    def reset(self) -> None:
        self.records = []
        self._next_id = 1

    def add(self, stage, source, action, candidate_answer="",
            rationale_or_review="", parent_event_id=None,
            evaluator_signal="") -> Optional[Dict[str, Any]]:
        normalized = normalize_candidate_answer(candidate_answer, rationale_or_review)
        record = {
            "event_id": self._next_id,
            "stage": str(stage or ""),
            "source": str(source or "unknown"),
            "action": str(action or ""),
            "candidate_answer": normalized,
            "rationale_or_review": compact_text(rationale_or_review, 240),
            "parent_event_id": parent_event_id,
            "evaluator_signal": str(evaluator_signal or ""),
        }
        self._next_id += 1
        self.records.append(record)
        if len(self.records) > self.limit:
            self.records = self.records[-self.limit:]
        return record

    def render(self) -> str:
        if not self.records:
            return ("Candidate And Revision Memory For This Question:\n"
                    "[No candidate or revision events yet.]")
        lines = [
            "Candidate And Revision Memory For This Question:",
            "Use this concise ledger to track proposed answers, reviews, revisions, and submitted candidates.",
            "Peer and Reviewer revisions are suggestions to verify; evaluator feedback is higher-priority but still non-leaking.",
        ]
        for record in self.records:
            header = "- C%s %s by %s" % (record["event_id"], record["action"], record["source"])
            if record["parent_event_id"] is not None:
                header += " revising C%s" % record["parent_event_id"]
            lines.append("")
            lines.append(header)
            lines.append("  candidate=%s" % record["candidate_answer"])
            if record["evaluator_signal"]:
                lines.append("  evaluator_signal=%s" % record["evaluator_signal"])
            if record["rationale_or_review"]:
                lines.append("  note=%s" % compact_text(record["rationale_or_review"], 180))
        return "\n".join(lines).strip()

    def render_for_evaluator_hint(self, max_records: int = 5) -> str:
        if not self.records:
            return "[No previous candidate/revision trajectory for this question.]"
        lines = ["Previous reasoning summary for evaluator hint generation:"]
        for record in self.records[-max(1, int(max_records or 1)):]:
            lines.append("- C%s: %s by %s; candidate=%s"
                         % (record["event_id"], record["action"], record["source"],
                            record["candidate_answer"]))
            if record["rationale_or_review"]:
                lines.append("  note=%s" % compact_text(record["rationale_or_review"], 160))
        return "\n".join(lines).strip()

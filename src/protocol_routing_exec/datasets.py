"""Dataset loading and field mapping.

The runner consumes JSONL with a normalized internal schema:

    {"id", "input", "answer", "reference_solution", "metadata": {...}}

Two loaders exist upstream and they disagree on answer-field priority. Both are
reproduced exactly, because picking the wrong one silently changes the gold
answer for thousands of rows:

  * ``omni-math``  (dataloader/omni_math.py) prefers ``answer_number`` OVER
    ``answer``. Omni-MATH-2 rows frequently have ``answer: null`` with the real
    value in ``answer_number``, so this ordering is load-bearing.
  * ``jsonl``      (agentverse_command/config_resolver.py::GenericJsonlLoader)
    prefers ``answer`` OVER ``answer_number``. Used for LAB-Bench, JEEBench and
    SciBench.

No benchmark problem text ships with this package. The dataset configs say how
to obtain and build each slice; you supply the files.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterator, List, Optional


class DatasetError(RuntimeError):
    pass


def _first_non_empty(row: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        if key not in row:
            continue
        value = row[key]
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_omni_math(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Port of dataloader/omni_math.py::_normalize_record."""
    question = _first_non_empty(row, ["question", "problem"])
    answer = _first_non_empty(row, ["answer_number", "answer", "label"])
    reference = _first_non_empty(row, ["equation_solution", "equation_answer", "solution"])
    metadata = {}
    for key in ("dataset_name", "source", "difficulty", "difficulty_tier",
                "domain", "judge_type", "raw_difficulty"):
        if key in row and row[key] is not None:
            metadata[key] = row[key]
    return {
        "id": str(row.get("id") or "omnimath_%06d" % index),
        "input": question,
        "answer": answer,
        "reference_solution": reference,
        "metadata": metadata,
    }


def _normalize_generic_jsonl(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Port of config_resolver.py::GenericJsonlLoader.load.

    NOTE the OPPOSITE answer priority to the omni-math loader.
    """
    question = _first_non_empty(row, ["input", "question", "problem"])
    answer = _first_non_empty(row, ["answer", "answer_number", "label"])
    reference = _first_non_empty(row, ["reference_solution", "solution"])
    metadata = {k: v for k, v in row.items()
                if k not in {"input", "question", "problem", "answer",
                             "answer_number", "label", "reference_solution",
                             "solution", "id", "tools"}}
    return {
        "id": str(row.get("id") or "row_%06d" % index),
        "input": question,
        "answer": answer,
        "reference_solution": reference,
        "metadata": metadata,
    }


LOADERS = {
    "omni-math": _normalize_omni_math,
    "jsonl": _normalize_generic_jsonl,
}


def normalize_loader_name(value: Optional[str]) -> str:
    """Port of config_resolver.py::normalize_dataset_loader aliases."""
    name = str(value or "jsonl").strip().lower().replace("_", "-")
    if name in {"omni-math-2-filtered", "omni-math-rule", "omnimath", "omni-math"}:
        return "omni-math"
    if name in {"generic", "generic-jsonl", "jsonl"}:
        return "jsonl"
    raise DatasetError(
        "Unsupported dataset loader %r. This package supports 'omni-math' and "
        "'jsonl' -- the two the paper protocols actually used." % value)


def resolve_path(path: str) -> str:
    """Expand ``$DATA_ROOT`` and ``~`` in a dataset path."""
    expanded = os.path.expandvars(os.path.expanduser(str(path or "")))
    if "$" in expanded:
        raise DatasetError(
            "Dataset path still contains an unexpanded variable after expansion: %r. "
            "Set DATA_ROOT (see .env.example) or give an absolute path." % expanded)
    return expanded


def load_dataset(dataset_config: Dict[str, Any], limit: int = 0) -> List[Dict[str, Any]]:
    loader_name = normalize_loader_name(dataset_config.get("loader"))
    normalize = LOADERS[loader_name]
    path = resolve_path(dataset_config.get("path", ""))
    if not path:
        raise DatasetError("Dataset config has no 'path'.")
    if not os.path.exists(path):
        raise DatasetError(
            "Dataset file not found: %s\nThis package ships no benchmark text. "
            "Build the slice with the upstream recipe named in the dataset config "
            "('obtain' section), then point 'path' at the result." % path)

    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except ValueError as exc:
                raise DatasetError("Invalid JSONL at %s:%d: %s" % (path, line_no, exc))
            record = normalize(raw, len(rows))
            if not record["input"]:
                raise DatasetError("Row %d in %s has no question text." % (line_no, path))
            if not record["answer"]:
                raise DatasetError(
                    "Row %d in %s has no gold answer under any of the expected fields. "
                    "Check that you used the '%s' loader for this file."
                    % (line_no, path, loader_name))
            rows.append(record)
            if limit and len(rows) >= limit:
                break

    expected = dataset_config.get("expected_rows")
    if expected and not limit and len(rows) != int(expected):
        raise DatasetError(
            "Row count mismatch for %s: loaded %d, config expects %d. Either the "
            "slice was built differently or the wrong file is configured. Fix the "
            "slice rather than editing expected_rows."
            % (path, len(rows), int(expected)))
    return rows


def dataset_fingerprint(rows: List[Dict[str, Any]]) -> str:
    """SHA-256 over (id, sha256(input), sha256(answer)) for every row.

    Recorded in the manifest so two runs can be shown to have used the same
    data WITHOUT the manifest containing any problem text or gold answer.
    """
    hasher = hashlib.sha256()
    for row in rows:
        hasher.update(str(row["id"]).encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(hashlib.sha256(row["input"].encode("utf-8")).hexdigest().encode())
        hasher.update(b"\x00")
        hasher.update(hashlib.sha256(row["answer"].encode("utf-8")).hexdigest().encode())
        hasher.update(b"\n")
    return "sha256:" + hasher.hexdigest()


def leakage_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Confirm no gold answer or outcome label rides inside the prompt text.

    Mirrors the ``input_leakage_check`` in the released confidence-probe runner.
    The solver prompt is built from ``input`` only; ``answer`` and
    ``reference_solution`` go to the evaluator alone. This check verifies the
    separation actually holds for the loaded rows.
    """
    forbidden = {"baseline_correct", "single_correct", "per_correct",
                 "broadcast_correct", "oracle_cheapest_successful",
                 "any_protocol_solved", "gold_answer", "answer_key",
                 "correct_answer", "protocol_outcomes"}
    errors: List[str] = []
    for idx, row in enumerate(rows):
        leaked = forbidden.intersection(row.get("metadata", {}) or {})
        if leaked:
            errors.append("row %d: outcome label leaked into metadata: %s"
                          % (idx, sorted(leaked)))
        answer = str(row.get("answer", "")).strip()
        if answer and len(answer) >= 3 and answer in row.get("input", ""):
            # Not necessarily a bug (the gold string can legitimately appear in
            # a multiple-choice option list), so this is a warning, not a fail.
            errors.append("row %d: WARNING gold answer string occurs in the prompt "
                          "text (expected for multiple-choice, suspicious otherwise)"
                          % idx)
    hard_failures = [e for e in errors if "WARNING" not in e]
    return {"passed": not hard_failures, "n_rows_checked": len(rows),
            "errors": errors[:50]}

"""Run-artifact writing: resolved config, manifest, environment, checksums.

Every run directory contains, without exception:

    resolved_config.yaml   fully merged config actually used (NO API KEY)
    manifest.json          run identity, counts, aggregate tokens, timings
    environment.json       interpreter, platform, package versions, git commit
    predictions.jsonl      one row per problem: answer, verdict, tokens, events
    answers.csv            flat per-problem table for quick inspection
    token_counts.json      aggregate and per-role token accounting
    evaluation.json        parse and evaluation summary
    run.log                human-readable log of the run
    checksums.sha256       sha256 of every other file in the directory

The resolved config is written BEFORE any model call, so a crashed run still
documents what it was trying to do.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from . import OUTPUT_SCHEMA_VERSION, __version__

# Keys that must never reach an artifact, checked recursively before writing.
SECRET_KEY_NAMES = {"api_key", "apikey", "token", "access_token", "secret",
                    "password", "authorization", "bearer", "base_url"}


def utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def scrub_secrets(payload: Any, path: str = "") -> List[str]:
    """Return a list of paths at which a secret-looking key holds a value.

    Note ``base_url`` is included: a private endpoint URL is as sensitive as a
    key for this release, and the provider layer records only env var NAMES.
    """
    findings: List[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = "%s.%s" % (path, key) if path else str(key)
            if str(key).strip().lower() in SECRET_KEY_NAMES:
                if isinstance(value, str) and value.strip():
                    findings.append(here)
                elif isinstance(value, (dict, list)) and value:
                    findings.append(here)
            findings.extend(scrub_secrets(value, here))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            findings.extend(scrub_secrets(item, "%s[%d]" % (path, idx)))
    return findings


def git_commit(repo_dir: Optional[str] = None) -> Optional[str]:
    """Best-effort code commit for the resolved config. None when unavailable."""
    target = repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.check_output(
            ["git", "-C", target, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip() or None
    except Exception:
        return None


def write_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def write_yaml(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        if yaml is not None:
            yaml.safe_dump(payload, handle, default_flow_style=False, sort_keys=True,
                           allow_unicode=True)
        else:  # pragma: no cover
            json.dump(payload, handle, indent=2, sort_keys=True)


def environment_snapshot() -> Dict[str, Any]:
    packages = {}
    for name in ("yaml", "openai", "requests", "numpy"):
        try:
            module = __import__(name)
            packages[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            packages[name] = None
    return {
        "captured_at_utc": utc_now(),
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "packages": packages,
        "protocol_routing_exec_version": __version__,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "note": ("Recorded for the machine that RAN this. It says nothing about "
                 "the machine that served the model."),
    }


def build_resolved_config(*, dataset_cfg, model_cfg, protocol_cfg, provider_desc,
                          decoding, seed, limit, output_dir, dataset_version,
                          dataset_fingerprint_value, prompt_version,
                          code_commit) -> Dict[str, Any]:
    """The reproducibility record. Must contain no credential of any kind."""
    resolved = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "runner_version": __version__,
        "timestamp_utc": utc_now(),
        "code_commit": code_commit,
        "seed": seed,
        "limit": limit or None,
        "output_dir": output_dir,
        "dataset": {
            "id": dataset_cfg.get("dataset_id"),
            "loader": dataset_cfg.get("loader"),
            "path": dataset_cfg.get("path"),
            "version": dataset_version,
            "upstream": dataset_cfg.get("obtain", {}).get("upstream_url"),
            "upstream_revision": dataset_cfg.get("obtain", {}).get("pinned_revision"),
            "expected_rows": dataset_cfg.get("expected_rows"),
            "fingerprint": dataset_fingerprint_value,
        },
        "model": {
            "id": model_cfg.get("model_id"),
            "revision": model_cfg.get("model_revision"),
            "revision_status": model_cfg.get("model_revision_status"),
            "family": model_cfg.get("family"),
        },
        "provider": provider_desc,
        "protocol": {
            "id": protocol_cfg.get("protocol_id"),
            "name": protocol_cfg.get("name"),
            "max_rounds": protocol_cfg.get("max_rounds"),
            "rule": protocol_cfg.get("rule"),
            "roles": sorted((protocol_cfg.get("roles") or {}).keys()),
            "peers": [p.get("name") for p in (protocol_cfg.get("peers") or [])],
            "provenance": protocol_cfg.get("provenance"),
        },
        "prompt_version": prompt_version,
        "decoding": decoding,
    }
    leaks = scrub_secrets(resolved)
    if leaks:
        raise RuntimeError(
            "Refusing to write resolved_config: secret-looking values present at %s"
            % leaks)
    return resolved


def write_checksums(output_dir: str, filename: str = "checksums.sha256") -> str:
    """Hash every file in the run directory except the checksum file itself."""
    target = os.path.join(output_dir, filename)
    entries = []
    for root, _dirs, files in os.walk(output_dir):
        for name in sorted(files):
            if name == filename:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, output_dir)
            hasher = hashlib.sha256()
            with open(full, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    hasher.update(chunk)
            entries.append((rel, hasher.hexdigest()))
    with open(target, "w", encoding="utf-8") as handle:
        for rel, digest in sorted(entries):
            handle.write("%s  %s\n" % (digest, rel))
    return target


class RunLogger(object):
    """Tee to stdout and run.log."""

    def __init__(self, path: str, echo: bool = True):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._handle = open(path, "a", encoding="utf-8")
        self._echo = echo

    def __call__(self, message: str) -> None:
        line = "[%s] %s" % (utc_now(), message)
        self._handle.write(line + "\n")
        self._handle.flush()
        if self._echo:
            print(line, flush=True)

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception:
            pass


def write_answers_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    fields = ["problem_id", "protocol", "final_answer", "passed", "correctness",
              "rounds_used", "stop_reason", "judge_calls", "direct_protocol_fail",
              "prompt_tokens", "completion_tokens", "total_tokens", "llm_calls",
              "wall_seconds"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

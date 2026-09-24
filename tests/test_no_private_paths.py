"""Fail if a private path, private URL, credential, or internal term appears in
public files.

This test exists because a release is a one-way door: once a private HPC path or
an internal codename is pushed to a public repository, it is in the git history
forever. The allowlist below is deliberately tiny -- provenance documents are
the only place a historical location may legitimately be named, and even there
it must be a stable identifier rather than a filesystem path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Only these files may mention a historical location, and only descriptively.
ALLOWLISTED = {
    # Provenance records may name a historical location, because saying where a
    # number came from is the point of them. Everything else must be portable.
    "docs/provenance/source_inventory.csv",
    "docs/provenance/code_extraction_map.csv",
    "docs/provenance/post_review_to_release_map.csv",
    "docs/provenance/historical_locations.md",
}

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv",
             "venv", "outputs", "data", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".zst",
                 ".parquet", ".zip", ".woff", ".woff2", ".pyc", ".so"}

FORBIDDEN = [
    ("private home path",      re.compile(r"/Users/[A-Za-z0-9._-]+")),
    ("linux home path",        re.compile(r"/home/[A-Za-z0-9._-]+")),
    ("HPC lustre path",        re.compile(r"/lus/[A-Za-z0-9._/-]+")),
    ("HPC eagle path",         re.compile(r"(?<![A-Za-z0-9_])/eagle/[A-Za-z0-9._/-]+")),
    ("HPC grand path",         re.compile(r"(?<![A-Za-z0-9_])/grand/[A-Za-z0-9._/-]+")),
    ("HPC flare path",         re.compile(r"(?<![A-Za-z0-9_])/flare/[A-Za-z0-9._/-]+")),
    ("internal host",          re.compile(r"\b(?:aurora|polaris|sophia|crux)[-.a-z0-9]*\.(?:alcf\.)?anl\.gov")),
    ("scheduler job id",       re.compile(r"\b\d{6,}\.(?:aurora|polaris|sophia)-pbs")),
    ("openai key",             re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("hugging face token",     re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("github token",           re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws key",                re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer token",           re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}")),
    ("private key block",      re.compile(r"BEGIN (?:RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY")),
    ("inline credential",      re.compile(r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)"
                                          r"\s*[=:]\s*[\"'][^\"'$<{][^\"']{7,}[\"']", re.I)),
    # The project was renamed. The old name must not appear in reader-facing text.
    # A verbatim historical git branch name inside a provenance record is the one
    # exception: altering it would make the provenance unverifiable.
    ("superseded project name", re.compile(
        r"[Tt]race2[Tt]raining(?!-rebuttal-\d{4}-\d{2}-\d{2})")),
    ("private source repo",    re.compile(r"github\.com[/:]ChihHsuan-Yang/(?:mas-eval|Emnlp_2026_mas_router)")),
]

# A .env.example is supposed to show variable NAMES, never values.
ENV_EXAMPLE_VALUE = re.compile(r"^\s*([A-Z_]+)\s*=\s*(\S+)\s*$")


def _public_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLISTED or rel == "tests/test_no_private_paths.py":
            continue
        yield path, rel


@pytest.mark.parametrize("label,pattern", FORBIDDEN, ids=[f[0] for f in FORBIDDEN])
def test_no_forbidden_pattern(label, pattern):
    hits = []
    for path, rel in _public_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                hits.append(f"{rel}:{lineno}: {match.group(0)[:80]}")
    assert not hits, (
        f"Forbidden pattern '{label}' found in public files:\n  "
        + "\n  ".join(hits[:20])
    )


def test_env_example_has_no_real_values():
    """.env.example must declare names with empty or placeholder values."""
    example = REPO_ROOT / ".env.example"
    if not example.exists():
        pytest.skip(".env.example not present")
    offenders = []
    for lineno, line in enumerate(example.read_text().splitlines(), start=1):
        if line.strip().startswith("#") or not line.strip():
            continue
        m = ENV_EXAMPLE_VALUE.match(line)
        if m:
            value = m.group(2)
            placeholder = (
                value.startswith(("<", "${", '"<', "/path/", "./", "path/"))
                or value in {'""', "''"}
                or value.startswith("https://provider.example")
                or value.startswith("https://huggingface.co")
            )
            if not placeholder:
                offenders.append(f"{lineno}: {line.strip()[:80]}")
    assert not offenders, (
        ".env.example appears to contain real values rather than placeholders:\n  "
        + "\n  ".join(offenders)
    )


def test_mascqa_appears_only_as_a_documented_exclusion():
    """MaScQA is excluded from the paper and the release.

    Naming it in a "what is not released" list is correct and wanted; shipping it
    as data, a config, or a result row is not. So this checks the CONTEXT of each
    mention rather than banning the string outright -- a blanket ban would push
    authors to quietly drop the disclosure, which is the opposite of the goal.
    """
    exclusion_context = re.compile(
        r"exclud|not released|omitted|no matched|noncommercial|non-commercial"
        r"|NC-SA|do not (?:include|release)|unavailable",
        re.I,
    )
    offenders = []
    for path, rel in _public_files():
        if path.suffix.lower() in {".csv", ".json", ".jsonl", ".yaml", ".yml"}:
            # Structured data may reference it only in a row that marks it excluded.
            strict = True
        else:
            strict = False
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if not re.search(r"\bMaScQA\b", line, re.I):
                continue
            window = " ".join(lines[max(0, lineno - 3):lineno + 2])
            if strict:
                ok = bool(exclusion_context.search(line))
            else:
                ok = bool(exclusion_context.search(window))
            if not ok:
                offenders.append(f"{rel}:{lineno}: {line.strip()[:90]}")
    assert not offenders, (
        "MaScQA mentioned outside an explicit exclusion context "
        "(it must never appear as released content):\n  " + "\n  ".join(offenders[:20])
    )


def test_no_committed_dotenv():
    committed = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.rglob(".env*")
        if p.is_file() and p.name != ".env.example"
        and ".git" not in p.parts
    ]
    assert not committed, f"A real .env file must never be committed: {committed}"

"""Every path a shipped config points at must exist in the repository.

This test exists because a documented command failed on a fresh clone: the
tiny-fixture dataset config pointed at ``fixtures/tiny_math.jsonl`` while the
file is at ``tests/fixtures/tiny_math.jsonl``. Nothing caught it, because the
test suite never loaded that config through the runner and the smoke target
used a different entry point. A config that names a file which is not there is
a broken command in the documentation, so it is checked here.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "configs"

# Keys whose values are repository-relative paths that must exist. Config keys
# that name an UPSTREAM resource (a benchmark we do not redistribute) are not
# in this list: those legitimately point at something the user must fetch.
LOCAL_PATH_KEYS = {"path", "prompt_file", "fixture", "local_path"}


def _config_files():
    return sorted(CONFIG_ROOT.rglob("*.yaml"))


def test_there_are_configs_to_check():
    """Guard against this whole file silently passing on an empty set."""
    assert _config_files(), "no configs found; the glob or the layout changed"


@pytest.mark.parametrize(
    "config_path", _config_files(), ids=lambda p: p.relative_to(CONFIG_ROOT).as_posix()
)
def test_local_paths_in_config_exist(config_path):
    data = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(data, dict):
        pytest.skip("config is not a mapping")

    missing = []

    def walk(node, trail):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in LOCAL_PATH_KEYS and isinstance(value, str) and value:
                    # Not a repo-relative file: an absolute path, a URL, or a
                    # path the user supplies at runtime through a variable.
                    # Upstream benchmark slices legitimately use ${DATA_ROOT},
                    # because this release does not redistribute their text.
                    if value.startswith(("/", "http://", "https://", "hf:")):
                        continue
                    if "${" in value or value.startswith("$"):
                        continue
                    if not (REPO_ROOT / value).exists():
                        missing.append(f"{'.'.join(trail + [key])} -> {value}")
                else:
                    walk(value, trail + [str(key)])
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, trail + [str(i)])

    walk(data, [])
    assert not missing, (
        f"{config_path.relative_to(REPO_ROOT)} names files that do not exist:\n  "
        + "\n  ".join(missing)
    )

"""Path handling and small CSV helpers.

There are deliberately NO hardcoded absolute paths in this package.  Every
input location arrives from a CLI argument or a config file.  The only
directory this module knows how to find on its own is the package's own
``configs/`` tree, resolved relative to the installed package.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
import yaml


def resolve(path: str | Path) -> Path:
    """Expand ``~`` and make a path absolute without requiring it to exist."""
    return Path(path).expanduser().resolve()


def require_file(path: str | Path, *, what: str = "file") -> Path:
    """Resolve a path and fail loudly if it is not an existing file."""
    resolved = resolve(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Missing {what}: {resolved}")
    return resolved


def require_dir(path: str | Path, *, what: str = "directory") -> Path:
    resolved = resolve(path)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Missing {what}: {resolved}")
    return resolved


def ensure_dir(path: str | Path) -> Path:
    resolved = resolve(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def repo_configs_dir() -> Path:
    """Locate the shipped ``configs/`` tree.

    Works both from a source checkout (``<repo>/configs``) and from an
    installed package that ships ``protocol_routing/configs``.
    """
    packaged = Path(__file__).resolve().parent / "configs"
    if packaged.is_dir():
        return packaged
    # src/protocol_routing/io.py -> src/protocol_routing -> src -> <repo>
    candidate = Path(__file__).resolve().parents[2] / "configs"
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(
        "Could not locate the configs/ directory. Pass an explicit --configs_dir."
    )


def read_yaml(path: str | Path) -> dict[str, Any]:
    with require_file(path, what="YAML config").open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a mapping at the top level of {path}")
    return loaded


def read_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(require_file(path, what="CSV"), **kwargs)


def write_csv(path: str | Path, rows: Iterable[dict[str, Any]], *, fieldnames: Sequence[str] | None = None) -> Path:
    """Write dict rows to CSV with a stable column order."""
    rows = list(rows)
    if not rows:
        raise ValueError(f"Refusing to write an empty CSV to {path}")
    names = list(fieldnames) if fieldnames is not None else list(rows[0].keys())
    target = resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    return target


def write_json(path: str | Path, payload: Any) -> Path:
    target = resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return target


def write_frame(path: str | Path, frame: pd.DataFrame) -> Path:
    target = resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target

"""Shared fixtures. Everything here is tiny and synthetic; nothing touches the network."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def toy_frame() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_DIR / "toybench__text_only__toy_solver_a.csv")


@pytest.fixture()
def both_toy_frames() -> list[pd.DataFrame]:
    return [pd.read_csv(p) for p in sorted(FIXTURE_DIR.glob("toybench__*.csv"))]

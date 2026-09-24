"""Make ``protocol_routing`` importable when running from a source checkout.

Installed users (``pip install -e .``) do not need this; it exists so that
``python scripts/X.py`` works in a fresh clone before any install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

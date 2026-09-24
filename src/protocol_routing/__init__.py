"""protocol_routing: offline analysis code for cost-aware protocol routing.

Companion code for the EMNLP 2026 paper

    "LLMs Can Predict Failure Risk, But Struggle to Predict Which
     Collaboration Protocol Pays Off: Cost-Aware Protocol Routing Across
     Reasoning Tasks."

This package implements the OFFLINE half of the pipeline: everything that can
be recomputed from released per-problem outcome tables without calling a model
endpoint.  Protocol *execution* (actually running Baseline / Single / PER /
Broadcast against an LLM) is not implemented here; see ``configs/protocols/``
and the README section "Inference-requiring steps".
"""

from __future__ import annotations

__version__ = "0.1.0"

from protocol_routing.oracle import (  # noqa: F401
    cheapest_successful_protocol,
    oracle_label_series,
)
from protocol_routing.protocols import (  # noqa: F401
    ORACLE_ORDER,
    PROTOCOL_COLORS,
    PROTOCOL_DISPLAY,
    PROTOCOL_ORDER,
    Protocol,
    canonical_protocol,
)

__all__ = [
    "__version__",
    "ORACLE_ORDER",
    "PROTOCOL_COLORS",
    "PROTOCOL_DISPLAY",
    "PROTOCOL_ORDER",
    "Protocol",
    "canonical_protocol",
    "cheapest_successful_protocol",
    "oracle_label_series",
]

"""Portable re-implementation of the four collaboration protocols.

Companion code for "LLMs Can Predict Failure Risk, But Struggle to Predict Which
Collaboration Protocol Pays Off: Cost-Aware Protocol Routing Across Reasoning
Tasks" (arXiv 2608.14927).

This package is Track B of the release: it RUNS the protocols against any
OpenAI-compatible endpoint. Track A (offline analysis of the released outcome
tables) is separate and does not require an endpoint.

Scope note, read this before comparing numbers to the paper:
    This is a portable re-implementation of the protocol semantics, derived from
    the original AgentVerse-based research engine. It reproduces the control
    flow, prompts, stopping rules and evaluator contract. It is NOT the original
    engine, and the original serving environment and model snapshots no longer
    exist. See docs/track_b_requirements.md for the three-way distinction
    between exact reproduction, functional rerun, and exact historical
    execution.
"""

__version__ = "0.1.0"
OUTPUT_SCHEMA_VERSION = "trackb-run-v1"

__all__ = ["__version__", "OUTPUT_SCHEMA_VERSION"]

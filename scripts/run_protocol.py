#!/usr/bin/env python3
"""Thin entry point. Equivalent to `python -m protocol_routing_exec.run_protocol`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from protocol_routing_exec.run_protocol import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

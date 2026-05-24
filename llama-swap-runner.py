#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pyyaml",
# ]
# ///

"""
Standalone runner for llama-swap CLI.

Usage:
    python llama-swap-runner.py ensure
    python llama-swap-runner.py config
    python llama-swap-runner.py start
    python llama-swap-runner.py status
    python llama-swap-runner.py logs
    python llama-swap-runner.py version
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llama_swap.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# ///

from lm_launcher.serve_observability import main


if __name__ == "__main__":
    raise SystemExit(main())

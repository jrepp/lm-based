#!/usr/bin/env -S uv run

from lm_launcher.serve_observability import main


if __name__ == "__main__":
    raise SystemExit(main())

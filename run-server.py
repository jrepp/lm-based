#!/usr/bin/env -S uv run --python 3.11 --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pydantic>=2.11,<3",
#   "pydantic-settings>=2.10,<3",
# ]
# ///

from lm_launcher.launcher import main


if __name__ == "__main__":
    main()

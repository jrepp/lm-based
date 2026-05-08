#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pyyaml",
# ]
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from llama_swap.bin import download_url, ensure_binary, find_binary, install_binary
from llama_swap.config import build_config, config_to_yaml, write_config
from llama_swap.wrapper import LlamaSwap

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def cmd_ensure(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="llama-swap ensure")
    parser.add_argument("--version", default="v209")
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = install_binary(dest=args.dest, version=args.version, overwrite=args.overwrite)
        print(f"Installed: {path}")
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def cmd_config(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="llama-swap config")
    parser.add_argument("--yaml", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cfg = build_config(PROJECT_ROOT / "models")
    if args.yaml:
        print(config_to_yaml(cfg))
    else:
        path = write_config(cfg, args.output or PROJECT_ROOT / "llama-swap.yaml")
        print(f"Written: {path}")
    return 0


def cmd_start(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="llama-swap start")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--listen", default="127.0.0.1:8080")
    parser.add_argument("--watch-config", action="store_true")
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    config_path = args.config or PROJECT_ROOT / "llama-swap.yaml"
    if not config_path.exists():
        print(f"error: config not found: {config_path}", file=sys.stderr)
        print(f"Run: llama-swap config --output {config_path}", file=sys.stderr)
        return 1

    swap = LlamaSwap(
        config_path=config_path,
        listen=args.listen,
        watch_config=args.watch_config,
        log_level=args.log_level,
    )
    try:
        swap.start(wait_ready=True, timeout=args.timeout)
        print(f"llama-swap running on {args.listen} (pid={swap.pid})")
        print(f"  config: {config_path}")
        print(f"  UI:     http://{args.listen}/ui")
        import time
        while swap.is_running:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        swap.stop()
    return 0


def cmd_status(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="llama-swap status")
    parser.add_argument("--listen", default="127.0.0.1:8080")
    args = parser.parse_args(argv)
    swap = LlamaSwap(listen=args.listen)
    running = swap.running_models()
    if not running:
        print("No models currently loaded.")
    else:
        print(f"{len(running)} model(s) loaded:")
        for m in running:
            print(f"  {m.get('id', '?')}")
    return 0


def cmd_logs(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="llama-swap logs")
    parser.add_argument("--listen", default="127.0.0.1:8080")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    swap = LlamaSwap(listen=args.listen)
    print(swap.logs(stream=args.stream, model_id=args.model), end="")
    return 0


def cmd_version(argv: list[str]) -> int:
    bin_path = find_binary()
    if not bin_path:
        print("llama-swap binary not found. Run: llama-swap ensure")
        return 1
    import subprocess
    result = subprocess.run([str(bin_path), "--version"], capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage llama-swap hot-swap proxy.",
        epilog=(
            "Commands:\n"
            "  ensure   Download and install the llama-swap binary\n"
            "  config   Generate llama-swap.yaml from model sidecars\n"
            "  start    Start llama-swap proxy\n"
            "  status   Show currently loaded models\n"
            "  logs     Print proxy or upstream logs\n"
            "  version  Print binary version\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["ensure", "config", "start", "status", "logs", "version"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv or sys.argv[1:])

    dispatch = {
        "ensure": cmd_ensure,
        "config": cmd_config,
        "start":  cmd_start,
        "status": cmd_status,
        "logs":   cmd_logs,
        "version": cmd_version,
    }
    return dispatch[parsed.command](parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
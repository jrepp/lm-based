"""Host audit for local model serving: who holds memory, and do the sidecars match the weights.

    just host-doctor     # or: uv run python -m lm_launcher.host_doctor

Read-only. Reports:
  - model servers listening on this host, marking those outside llama-swap
    (orphans keep their weights resident and are invisible to swap groups)
  - each server's memory footprint, and system wired memory against the GPU
    wired-memory limit (RSS misses Metal buffers, so wired memory is the budget)
  - sidecars whose model.context_length disagrees with the local GGUF header
Exit status is 1 when something needs attention.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lm_launcher.gguf_metadata import context_length as gguf_context_length

ROOT = Path(__file__).resolve().parents[1]

# Command-line patterns of processes that hold model weights.
MODEL_SERVER = re.compile(r"llama-server|mlx_lm[./]server|kev_serve|kev\.serve|ollama serve|transformers serve")
# macOS default GPU wired limit when iogpu.wired_limit_mb is 0 (about 75% of RAM).
DEFAULT_WIRED_FRACTION = 0.75

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    command: str


@dataclass(frozen=True)
class ModelServer:
    pid: int
    ports: tuple[int, ...]
    command: str
    under_llama_swap: bool


def parse_ps(text: str) -> dict[int, Process]:
    processes: dict[int, Process] = {}
    for line in text.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        processes[int(parts[0])] = Process(int(parts[0]), int(parts[1]), parts[2])
    return processes


def parse_lsof_listen(text: str) -> dict[int, tuple[int, ...]]:
    """`lsof -nP -iTCP -sTCP:LISTEN` -> pid -> listening ports."""
    ports: dict[int, set[int]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9 or not parts[1].isdigit():
            continue
        match = re.search(r":(\d+)$", parts[8])
        if match:
            ports.setdefault(int(parts[1]), set()).add(int(match.group(1)))
    return {pid: tuple(sorted(found)) for pid, found in ports.items()}


def has_ancestor(pid: int, processes: dict[int, Process], pattern: str) -> bool:
    seen: set[int] = set()
    current = processes.get(pid)
    while current and current.ppid not in seen and current.ppid > 1:
        seen.add(current.ppid)
        current = processes.get(current.ppid)
        if current and pattern in current.command:
            return True
    return False


def model_servers(processes: dict[int, Process], listening: dict[int, tuple[int, ...]]) -> list[ModelServer]:
    servers = []
    for pid, ports in listening.items():
        process = processes.get(pid)
        if process is None or not MODEL_SERVER.search(process.command):
            continue
        servers.append(
            ModelServer(
                pid=pid,
                ports=ports,
                command=process.command,
                under_llama_swap=has_ancestor(pid, processes, "llama-swap"),
            )
        )
    return sorted(servers, key=lambda server: (not server.under_llama_swap, server.ports))


def wired_limit_bytes(limit_mb: int, memsize: int) -> int:
    return limit_mb * 1024 * 1024 if limit_mb > 0 else int(memsize * DEFAULT_WIRED_FRACTION)


def parse_wired_bytes(vm_stat: str) -> int | None:
    page = re.search(r"page size of (\d+) bytes", vm_stat)
    wired = re.search(r"Pages wired down:\s+(\d+)", vm_stat)
    return int(page.group(1)) * int(wired.group(1)) if page and wired else None


def parse_footprint_bytes(text: str) -> int | None:
    match = re.search(r"phys_footprint:\s+([\d.]+)\s*(KB|MB|GB)", text)
    if not match:
        return None
    return int(float(match.group(1)) * {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[match.group(2)])


def sidecar_context_mismatches(models_dir: Path = ROOT / "models", artifacts: Path = ROOT / "artifacts") -> list[str]:
    problems = []
    for path in sorted(models_dir.glob("*.json")):
        record = json.loads(path.read_text())
        artifact = record.get("artifact", {})
        declared = record.get("model", {}).get("context_length")
        local = artifact.get("local_path")
        if artifact.get("format", "gguf") != "gguf" or not local or not isinstance(declared, int):
            continue
        weights = next((p for p in (ROOT / local, artifacts / local) if p.is_file()), None)
        if weights is None:
            continue
        try:
            actual = gguf_context_length(weights)
        except (OSError, ValueError) as error:
            problems.append(f"{path.name}: cannot read GGUF header ({error})")
            continue
        if actual is not None and actual != declared:
            problems.append(f"{path.name}: model.context_length {declared}, GGUF header says {actual}")
    return problems


def short_command(command: str, width: int = 70) -> str:
    """`<program> <model>`, naming the script rather than the interpreter for Python servers."""
    words = command.split()
    names = [word.rsplit("/", 1)[-1] for word in words]
    program = next((name for name in names if name.endswith(".py") or "server" in name or name == "ollama"), names[0] if names else "")
    model = re.search(r"--model\s+(\S+)", command)
    text = f"{program} {Path(model.group(1)).name}" if model else " ".join([program, *words[names.index(program) + 1:]][:3])
    return text if len(text) <= width else text[: width - 1] + "…"


def gib(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def run(runner: Runner = subprocess.run) -> int:
    ps = runner(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
    lsof = runner(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    sysctl = runner(["sysctl", "-n", "iogpu.wired_limit_mb", "hw.memsize"], capture_output=True, text=True).stdout.split()
    limit = wired_limit_bytes(int(sysctl[0]), int(sysctl[1])) if len(sysctl) == 2 else 0

    attention = False
    servers = model_servers(parse_ps(ps), parse_lsof_listen(lsof))
    print("model servers:")
    if not servers:
        print("  (none listening)")
    for server in servers:
        where = "llama-swap" if server.under_llama_swap else "OUTSIDE llama-swap"
        ports = ",".join(str(port) for port in server.ports)
        footprint = parse_footprint_bytes(
            runner(["footprint", "-p", str(server.pid)], capture_output=True, text=True).stdout
        )
        size = gib(footprint) if footprint is not None else "?"
        print(f"  {server.pid:>6}  :{ports:<11} {size:>10}  {where:<18}  {short_command(server.command)}")
    if servers:
        print("  (memory = footprint: KV cache and private buffers; mapped weights are counted in wired memory)")
    orphans = [server for server in servers if not server.under_llama_swap]
    if orphans:
        attention = True
        print(f"  ! {len(orphans)} server(s) outside llama-swap keep weights resident and are not swapped out;")
        print("    stop them if nothing else uses them (check with their owner first).")

    wired = parse_wired_bytes(runner(["vm_stat"], capture_output=True, text=True).stdout)
    if limit and wired is not None:
        share = wired / limit
        print(f"wired memory: {gib(wired)} of the {gib(limit)} GPU wired limit ({share:.0%})")
        if share > 0.9:
            attention = True
            print("  ! close to the wired limit; the next model load may fail or evict")

    mismatches = sidecar_context_mismatches()
    print("sidecar context vs GGUF headers:", "ok" if not mismatches else "")
    for problem in mismatches:
        attention = True
        print(f"  ! {problem}")
    return 1 if attention else 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

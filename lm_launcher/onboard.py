"""First-run setup for a new host: ./up init, ./up doctor, ./up pull.

Stdlib only: ``up`` runs as a uv script with just ``rich``.

``init`` sizes a starter model set to this machine's memory and writes it to the
gitignored ``serve-policy.local.yaml``. ``doctor`` checks prerequisites, the enabled
models on disk, and whether the largest model set fits the GPU memory budget.
``pull`` downloads the enabled models that are missing.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lm_launcher.artifacts import artifact_present, record_artifact_path
from lm_launcher.env_file import read_dotenv, setting
from lm_launcher.policy import LOCAL_POLICY_PATH, enabled_slugs, load_policy

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
GiB = 1024**3
# macOS lets the GPU wire about 75% of unified memory by default (iogpu.wired_limit_mb=0).
WIRED_FRACTION = 0.75


@dataclass(frozen=True)
class Preset:
    name: str
    min_memory_gb: int
    chat: tuple[str, ...]  # "main" group: one loaded at a time, swapped on demand
    resident: tuple[str, ...]  # "small" group: stays loaded beside the chat model
    summary: str


# Ordered smallest first. Models here run on stock llama-server builds (no MTP).
PRESETS: tuple[Preset, ...] = (
    Preset(
        name="compact",
        min_memory_gb=0,
        chat=("mistral-7b-instruct-v03-q4km",),
        resident=("glm-ocr-q8_0",),
        summary="Mistral 7B chat plus GLM-OCR (about 6 GB of weights)",
    ),
    Preset(
        name="standard",
        min_memory_gb=48,
        chat=("qwen35-35b-a3b-q4km", "qwen36-27b-q6k", "mistral-7b-instruct-v03-q4km"),
        resident=("glm-ocr-q8_0",),
        summary="Qwen3.5 35B-A3B and Qwen3.6 27B chat plus GLM-OCR (about 22 GB loaded)",
    ),
    Preset(
        name="workstation",
        min_memory_gb=96,
        chat=("qwen3-coder-next-iq4xs", "qwen35-35b-a3b-q4km", "qwen36-27b-q6k"),
        resident=("glm-ocr-q8_0",),
        summary="Qwen3-Coder-Next, Qwen3.5 35B-A3B, and Qwen3.6 27B plus GLM-OCR (about 45 GB loaded)",
    ),
)


def preset_by_name(name: str) -> Preset:
    for preset in PRESETS:
        if preset.name == name:
            return preset
    raise KeyError(name)


def choose_preset(memory_gb: float) -> Preset:
    chosen = PRESETS[0]
    for preset in PRESETS:
        if memory_gb >= preset.min_memory_gb:
            chosen = preset
    return chosen


def preset_overlay(preset: Preset) -> dict[str, Any]:
    """The serve-policy.local.yaml content for a preset."""
    groups: dict[str, Any] = {
        "main": {"swap": True, "exclusive": False, "members": list(preset.chat)},
    }
    if preset.resident:
        groups["small"] = {
            "swap": False,
            "exclusive": False,
            "persistent": False,
            "members": list(preset.resident),
        }
    return {
        "models": {"enabled": [*preset.chat, *preset.resident], "warm": []},
        "swap": {"routing": {"router": {"use": "group", "settings": {"groups": groups}}}},
    }


def host_memory_bytes() -> int | None:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            return int(out.stdout.strip())
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return None


def load_records(models_dir: Path = MODELS_DIR) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(models_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = record.get("model", {}).get("slug")
        if isinstance(slug, str) and slug:
            records[slug] = record
    return records


_SHARD = re.compile(r"^(?P<stem>.+)-00001-of-(?P<count>\d{5})\.gguf$")


def artifact_bytes(path: Path) -> int:
    """On-disk size of a model: all shards of a split GGUF, or the whole model directory."""
    if not path.exists():
        return 0
    shard = _SHARD.match(path.name)
    if shard:
        return sum(p.stat().st_size for p in path.parent.glob(f"{shard['stem']}-*-of-{shard['count']}.gguf"))
    if path.suffix == ".gguf":
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.parent.rglob("*") if p.is_file() and ".cache" not in p.parts)


def legacy_root_artifacts(records: dict[str, dict[str, Any]], root: Path = ROOT) -> list[str]:
    """Artifacts still at the project root from before downloads moved to artifacts/."""
    found = []
    for record in records.values():
        local_path = record.get("artifact", {}).get("local_path")
        if local_path and not Path(local_path).is_absolute() and (root / local_path).exists():
            found.append(Path(local_path).parts[0])
    return sorted(set(found))


# ─── init ─────────────────────────────────────────────────────────────────────


def init(preset_name: str | None = None, force: bool = False, out=sys.stdout) -> int:
    memory = host_memory_bytes()
    memory_gb = memory / GiB if memory else 0.0
    if preset_name:
        try:
            preset = preset_by_name(preset_name)
        except KeyError:
            print(f"error: unknown preset {preset_name!r}; choose from {', '.join(p.name for p in PRESETS)}", file=sys.stderr)
            return 2
    else:
        preset = choose_preset(memory_gb)

    if memory:
        print(f"host memory: {memory_gb:.0f} GB", file=out)
    else:
        print("host memory: unknown (pass --preset to choose)", file=out)

    if LOCAL_POLICY_PATH.exists() and not force:
        print(f"kept {LOCAL_POLICY_PATH.name} (already exists; --force replaces it)", file=out)
    else:
        LOCAL_POLICY_PATH.write_text(json.dumps(preset_overlay(preset), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {LOCAL_POLICY_PATH.name}: preset {preset.name!r}: {preset.summary}", file=out)

    env_path = ROOT / ".env"
    if not env_path.exists():
        shutil.copyfile(ROOT / ".env.example", env_path)
        print("wrote .env from .env.example", file=out)

    print("\nnext:", file=out)
    print("  ./up doctor   # check prerequisites and memory", file=out)
    print("  ./up pull     # download the enabled models", file=out)
    print("  ./up          # start llama-swap", file=out)
    return 0


# ─── doctor ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Check:
    status: str  # ok | warn | fail
    name: str
    detail: str


def _which(name: str) -> str | None:
    return shutil.which(name)


def _llama_server() -> str | None:
    configured = setting("LLAMA_SERVER_BIN", "llama-server") or "llama-server"
    expanded = os.path.expanduser(configured)
    if os.sep in expanded:
        return expanded if os.access(expanded, os.X_OK) else None
    return _which(expanded)


def _llama_swap() -> str | None:
    override = os.environ.get("LLAMA_SWAP_BIN")
    if override and Path(override).exists():
        return override
    local = ROOT / ".runtime" / "bin" / "llama-swap"
    return _which("llama-swap") or (str(local) if local.exists() else None)


def doctor_checks(
    policy: dict[str, Any] | None = None,
    records: dict[str, dict[str, Any]] | None = None,
    memory: int | None = None,
) -> list[Check]:
    policy = load_policy() if policy is None else policy
    records = load_records() if records is None else records
    memory = host_memory_bytes() if memory is None else memory
    enabled = enabled_slugs(policy)
    enabled_records = {slug: records[slug] for slug in enabled if slug in records}
    formats = {r.get("artifact", {}).get("format", "gguf") for r in enabled_records.values()}
    checks: list[Check] = []

    if sys.platform != "darwin" or platform.machine() != "arm64":
        checks.append(Check("warn", "platform", f"{sys.platform}/{platform.machine()}: built for Apple Silicon; MLX models will not run"))
    else:
        checks.append(Check("ok", "platform", "Apple Silicon macOS"))

    server = _llama_server()
    if server:
        checks.append(Check("ok", "llama-server", server))
    elif "gguf" in formats:
        checks.append(Check("fail", "llama-server", "not found: `brew install llama.cpp`, or set LLAMA_SERVER_BIN in .env"))
    else:
        checks.append(Check("warn", "llama-server", "not found (no enabled GGUF model needs it)"))

    swap = _llama_swap()
    checks.append(
        Check("ok", "llama-swap", swap)
        if swap
        else Check("warn", "llama-swap", "not found; `./llama-swap-runner.py ensure` installs it into .runtime/bin")
    )
    checks.append(
        Check("ok", "tmux", _which("tmux") or "")
        if _which("tmux")
        else Check("warn", "tmux", "not found; run services with `./up --foreground` or `brew install tmux`")
    )
    checks.append(
        Check("ok", "node", _which("node") or "")
        if _which("node")
        else Check("warn", "node", "not found; needed only for ./pi-local (`brew install node`)")
    )

    if LOCAL_POLICY_PATH.exists():
        checks.append(Check("ok", "policy", f"{LOCAL_POLICY_PATH.name} over serve-policy.yaml"))
    else:
        checks.append(Check("warn", "policy", "using the default serve-policy.yaml; `./up init` sizes it to this host"))

    if not enabled:
        checks.append(Check("fail", "models", "serve-policy enables no models"))
    for slug in enabled:
        record = records.get(slug)
        if record is None:
            checks.append(Check("fail", slug, "enabled in serve-policy but no sidecar in models/"))
        elif artifact_present(record):
            checks.append(Check("ok", slug, "downloaded"))
        else:
            checks.append(Check("warn", slug, "not downloaded; `./up pull` fetches it (llama-swap skips it until then)"))

    checks.append(_memory_check(policy, enabled_records, memory))

    legacy = legacy_root_artifacts(records)
    if legacy:
        checks.append(Check("ok", "layout", f"{len(legacy)} artifact(s) at the project root still load; new downloads go to artifacts/"))
    return checks


def _memory_check(policy: dict[str, Any], enabled_records: dict[str, dict[str, Any]], memory: int | None) -> Check:
    if not memory:
        return Check("warn", "memory", "cannot read host memory")
    budget = memory * WIRED_FRACTION
    sizes = {}
    for slug, record in enabled_records.items():
        path = record_artifact_path(record)
        sizes[slug] = artifact_bytes(path) if path else 0
    groups = policy.get("swap", {}).get("routing", {}).get("router", {}).get("settings", {}).get("groups", {})
    resident = sum(
        sizes.get(m, 0)
        for group in groups.values()
        if isinstance(group, dict) and not group.get("swap", True)
        for m in group.get("members", [])
    )
    swapped = [sizes.get(m, 0) for group in groups.values() if isinstance(group, dict) and group.get("swap", True) for m in group.get("members", [])]
    peak = resident + max(swapped, default=0) if groups else max(sizes.values(), default=0)
    detail = f"largest loaded set {peak / GiB:.1f} GB of weights vs ~{budget / GiB:.0f} GB GPU budget (downloaded models only; KV cache comes on top)"
    return Check("fail" if peak > budget else "ok", "memory", detail)


def doctor(out=sys.stdout) -> int:
    checks = doctor_checks()
    width = max(len(c.name) for c in checks)
    for check in checks:
        print(f"{check.status:4s}  {check.name:{width}s}  {check.detail}", file=out)
    failed = [c for c in checks if c.status == "fail"]
    print(f"\n{len(failed)} problem(s)" if failed else "\nready", file=out)
    return 1 if failed else 0


# ─── pull ─────────────────────────────────────────────────────────────────────


def pull() -> int:
    return subprocess.call([str(ROOT / "download_model.py"), "--enabled"], cwd=ROOT)

from __future__ import annotations

import os
import platform
import shutil
import stat
import urllib.request
from pathlib import Path

RELEASE_URL = "https://github.com/mostlygeek/llama-swap/releases/download/{version}/llama-swap-{platform}-{arch}"

PLATFORM_MAP = {
    "darwin": "darwin",
    "linux":  "linux",
    "windows": "windows",
}

ARCH_MAP = {
    "x86_64":  "amd64",
    "arm64":   "arm64",
    "aarch64": "arm64",
}

DEFAULT_VERSION = "v203"


def _system_platform() -> str:
    return PLATFORM_MAP.get(platform.system().lower(), "linux")


def _system_arch() -> str:
    return ARCH_MAP.get(platform.machine().lower(), "amd64")


def find_binary() -> Path | None:
    for name in ("llama-swap", "llama-swap.exe"):
        path = shutil.which(name)
        if path:
            return Path(path)
    return None


def download_url(version: str = DEFAULT_VERSION) -> str:
    plat = _system_platform()
    arch = _system_arch()
    name = f"llama-swap-{plat}-{arch}"
    if plat == "windows":
        name += ".exe"
    return RELEASE_URL.format(version=version, platform=plat, arch=arch)


def install_binary(
    dest: Path | None = None,
    version: str = DEFAULT_VERSION,
    overwrite: bool = False,
) -> Path:
    url = download_url(version)
    if dest is None:
        dest = Path(shutil.getprefix()) / "bin" / f"llama-swap.exe" if platform.system().lower() == "windows" else Path("/usr/local/bin/llama-swap")

    if dest.exists() and not overwrite:
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            fh.write(chunk)

    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dest


def ensure_binary() -> Path:
    found = find_binary()
    if found:
        return found
    dest = os.environ.get("LLAMA_SWAP_BIN")
    if dest:
        path = Path(dest)
        if path.exists():
            return path
        raise FileNotFoundError(f"$LLAMA_SWAP_BIN={dest} does not exist")
    return install_binary()

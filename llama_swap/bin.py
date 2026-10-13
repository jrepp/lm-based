from __future__ import annotations

import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RELEASE_URL = "https://github.com/mostlygeek/llama-swap/releases/download/{version}/{asset}"

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

DEFAULT_VERSION = "v264"


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


def _version_number(version: str) -> str:
    return version[1:] if version.startswith("v") else version


def download_urls(version: str = DEFAULT_VERSION) -> tuple[str, str]:
    """Candidate asset URLs, newest scheme first.

    v224+ ship versioned tarballs (llama-swap_<ver>_<plat>_<arch>.tar.gz under
    tag v<ver>); older releases exposed raw binaries named without the version.
    """
    plat = _system_platform()
    arch = _system_arch()
    ver = _version_number(version)
    exe = ".exe" if plat == "windows" else ""
    new = RELEASE_URL.format(version=version, asset=f"llama-swap_{ver}_{plat}_{arch}.tar.gz")
    old = RELEASE_URL.format(version=version, asset=f"llama-swap-{plat}-{arch}{exe}")
    return new, old


def download_url(version: str = DEFAULT_VERSION) -> str:
    return download_urls(version)[0]


def _extract_tarball(tar_path: Path, dest: Path) -> None:
    wanted = "llama-swap.exe" if dest.suffix == ".exe" else "llama-swap"
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.split("/")[-1] == wanted and member.isfile():
                src = tar.extractfile(member)
                if src is None:
                    break
                with dest.open("wb") as fh:
                    shutil.copyfileobj(src, fh)
                return
    raise ValueError(f"no {wanted} inside {tar_path.name}")


def _fetch(url: str, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            if url.endswith(".tar.gz"):
                with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                    shutil.copyfileobj(resp, tmp)
                    tmp_name = tmp.name
            else:
                with dest.open("wb") as fh:
                    shutil.copyfileobj(resp, fh)
                return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    try:
        _extract_tarball(Path(tmp_name), dest)
        return True
    finally:
        os.unlink(tmp_name)


def install_binary(
    dest: Path | None = None,
    version: str = DEFAULT_VERSION,
    overwrite: bool = False,
) -> Path:
    if dest is None:
        dest = Path(shutil.getprefix()) / "bin" / f"llama-swap.exe" if platform.system().lower() == "windows" else Path("/usr/local/bin/llama-swap")

    if dest.exists() and not overwrite:
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    new_url, old_url = download_urls(version)
    if not _fetch(new_url, dest):
        _fetch(old_url, dest)

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

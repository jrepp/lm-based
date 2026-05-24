from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from llama_swap.bin import ensure_binary, find_binary


class LlamaSwap:
    def __init__(
        self,
        config_path: Path | None = None,
        listen: str = "127.0.0.1:8080",
        watch_config: bool = False,
        log_level: str = "info",
        extra_args: list[str] | None = None,
    ):
        self._config_path = config_path or Path("llama-swap.yaml")
        self._listen = listen
        self._watch_config = watch_config
        self._log_level = log_level
        self._extra_args = extra_args or []
        self._process: Optional[subprocess.Popen[str]] = None
        self._pid: Optional[int] = None

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def _build_args(self) -> list[str]:
        bin_path = ensure_binary()
        args = [str(bin_path)]

        if self._config_path and self._config_path.exists():
            args.extend(["--config", str(self._config_path)])

        args.extend(["--listen", self._listen])

        if self._watch_config:
            args.append("--watch-config")

        if self._log_level:
            args.extend(["--log-level", self._log_level])

        args.extend(self._extra_args)
        return args

    def start(self, wait_ready: bool = True, timeout: float = 30.0) -> None:
        if self.is_running:
            raise RuntimeError("llama-swap is already running")

        args = self._build_args()
        self._process = subprocess.Popen(args, text=True)
        self._pid = self._process.pid

        if wait_ready:
            self._wait_until_ready(timeout)

    def _wait_until_ready(self, timeout: float) -> None:
        import urllib.request
        host_port = self._listen.split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 8080
        url = f"http://{host}:{port}/health"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError(f"llama-swap process exited unexpectedly: {self._process.returncode}")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "llama-swap-python/0.1"})
                with urllib.request.urlopen(req, timeout=2.0) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError(f"llama-swap did not become ready within {timeout}s")

    def stop(self, timeout: float = 10.0) -> None:
        if not self.is_running:
            return
        proc = self._process
        if proc is None:
            return
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def restart(self, wait_ready: bool = True, timeout: float = 30.0) -> None:
        if self.is_running:
            self.stop()
        self.start(wait_ready=wait_ready, timeout=timeout)

    def __enter__(self) -> "LlamaSwap":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def running_models(self) -> list[dict[str, object]]:
        import json, urllib.request
        host_port = self._listen.split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 8080
        url = f"http://{host}:{port}/running"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "llama-swap-python/0.1"})
            with urllib.request.urlopen(req, timeout=5.0) as r:
                return json.loads(r.read())
        except Exception:
            return []

    def logs(self, stream: bool = False, model_id: str | None = None) -> str:
        import urllib.request
        host_port = self._listen.split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 8080
        path = "/logs/stream" if stream else "/logs"
        if model_id:
            path = f"/logs/stream/{model_id}"
        url = f"http://{host}:{port}{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "llama-swap-python/0.1"})
            with urllib.request.urlopen(req, timeout=5.0) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            return f"# error fetching logs: {e}"

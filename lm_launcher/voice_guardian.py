"""Own a worker process group; parent pipe EOF also terminates it after server death."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from lm_launcher.voice_runtime import runtime_command
from lm_launcher.job_progress import write_json


def supervise(command: list[str], grace: float = 5, log_path: Path | None = None, *, cwd=None, env=None, heartbeat_path=None) -> int:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.set())

    def parent_watch():
        # This pipe is owned only by the service. No PID lookup or persisted PID killing.
        while os.read(sys.stdin.fileno(), 1):
            pass
        stop.set()

    threading.Thread(target=parent_watch, daemon=True).start()
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, start_new_session=True,
                             stdout=subprocess.PIPE if log_path else None, stderr=subprocess.STDOUT)
    reader = None
    if log_path:
        logger = logging.getLogger('worker')
        logger.setLevel(logging.INFO)
        sink = RotatingFileHandler(log_path, maxBytes=4 * 1024**2, backupCount=2)
        logger.addHandler(sink)

        def capture():
            while chunk := child.stdout.read1(8192):
                logger.info(chunk.decode(errors='replace').rstrip())

        reader = threading.Thread(target=capture, daemon=True)
        reader.start()
    stopped = False
    heartbeat_at = 0.0
    while child.poll() is None:
        if heartbeat_path and time.monotonic() - heartbeat_at >= 2:
            try:
                write_json(heartbeat_path, {'time': time.time()})
            except OSError:
                # Monitoring failure must not abandon our owned process group.
                pass
            heartbeat_at = time.monotonic()
        if stop.wait(.2):
            stopped = True
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + grace
            while child.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            # Also remove any subprocess left behind after its leader exits.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            break
    code = child.wait()
    # A finished command must not leave descendants running beyond its job lifetime.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if reader:
        reader.join(timeout=2)
        sink.close()
    return 130 if stopped else code


def main():
    directory = Path(sys.argv[1]).resolve(strict=True)
    request = json.loads((directory / 'request.json').read_text())
    started = time.time()
    command_job = request['kind'] == 'command'
    if command_job:
        write_json(directory / 'status.json', {'state': 'running', 'started_at': started})
    try:
        code = supervise(
            request['argv'] if command_job else runtime_command(request['kind'], directory),
            log_path=directory / 'job.log', cwd=request.get('cwd') if command_job else None,
            env={**os.environ, 'LM_JOB_ID': directory.name, 'LM_JOB_DIR': str(directory),
                 'LM_JOB_PROGRESS_FILE': str(directory / 'progress.json')},
            heartbeat_path=directory / 'heartbeat.json')
        if command_job:
            write_json(directory / 'status.json', {
                'state': 'completed' if code == 0 else 'failed', 'started_at': started,
                'result': {'exit_code': code, 'cwd': request['cwd']},
                'error': None if code == 0 else f'command exited with status {code}'})
    except Exception as exc:
        write_json(directory / 'status.json', {'state': 'failed', 'started_at': started, 'error': str(exc)})
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()

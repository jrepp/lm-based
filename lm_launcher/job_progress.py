"""Optional structured progress contract for any managed command.

Workers may also atomically replace LM_JOB_PROGRESS_FILE with JSON directly.
A heartbeat means the guardian is alive, not that the task is making progress.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time


def write_json(path: Path, value: dict):
    """Publish an atomic snapshot, including when multiple threads report progress."""
    fd, name = tempfile.mkstemp(prefix='.progress-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, allow_nan=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def report(stage: str, completed: float | None = None, total: float | None = None,
           message: str = ''):
    for value in (completed, total):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError('progress counts must be finite and nonnegative')
    if completed is not None and total is not None and completed > total:
        raise ValueError('completed cannot exceed total')
    write_json(Path(os.environ['LM_JOB_PROGRESS_FILE']), {
        'stage': stage, 'completed': completed, 'total': total, 'message': message,
        'updated_at': time.time(),
        'percent': 100 * completed / total if completed is not None and total else None,
    })

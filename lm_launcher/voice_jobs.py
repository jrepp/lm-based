"""Local task service: durable queue, owned workers, progress and voice adapters."""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

from lm_launcher.voice_runtime import ROOT, KINDS, GPU_KINDS

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted', 'expired'}
DEFAULT_ROOT = ROOT / '.runtime' / 'voice-workbench'
LOG = logging.getLogger('voice-jobs')


def event(name, **fields):
    LOG.info(json.dumps({'time': time.time(), 'event': name, **fields}, ensure_ascii=False))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


class JobStore:
    def __init__(self, root: Path, retention_days=7, queue_limit=64):
        self.root = root.resolve()
        self.jobs = self.root / 'jobs'
        self.jobs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.retention = retention_days * 86400
        self.queue_limit = queue_limit
        self.db = sqlite3.connect(self.root / 'index.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if self.db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
            self.db.close()
            raise ValueError('unsupported voice index schema version')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, request TEXT NOT NULL,
                result TEXT, error TEXT, dependencies TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
                bytes INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS voices (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, job_id TEXT,
                manifest TEXT NOT NULL, created REAL NOT NULL, legacy INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS cleanups (
                id INTEGER PRIMARY KEY, started REAL NOT NULL, finished REAL,
                dry_run INTEGER NOT NULL, state TEXT NOT NULL, result TEXT, error TEXT);
            PRAGMA user_version=1;
        ''')
        self.db.commit()

    def rows(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY created')]

    def recover(self):
        with self.lock, self.db:
            self.db.execute("UPDATE jobs SET state='interrupted', error='service stopped before completion; submit a new job to retry', updated=? WHERE state IN ('running','cancelling')", (time.time(),))
        with self.lock, self.db:
            self.db.execute("UPDATE cleanups SET state='interrupted', finished=?, error='service stopped during cleanup' WHERE state='running'", (time.time(),))
        # Recover completed train indexing after a crash between completion and indexing.
        for row in self.rows():
            if row['state'] == 'completed' and row['kind'] == 'train':
                self.index_voice(row['id'], self.jobs / row['id'] / 'trained-voice.json')
        # Legacy artifacts are indexed read-only and NEVER enrolled in automatic cleanup.
        for manifest in self.jobs.glob('job-*/trained-voice.json'):
            if not any(r['id'] == manifest.parent.name for r in self.rows()) and read_json(manifest.parent / 'status.json', {}).get('state') == 'completed':
                self.index_voice(manifest.parent.name, manifest, legacy=True)

    def index_voice(self, job_id, manifest, legacy=False):
        data = read_json(manifest)
        if not isinstance(data, dict) or not isinstance(data.get('model'), str) or not data['model'] or not Path(data['model']).is_dir() or not data.get('name'):
            return
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO voices VALUES (?,?,?,?,?,?)',
                            (job_id, data['name'], None if legacy else job_id, str(manifest), time.time(), int(legacy)))
            if not legacy:
                self.db.execute('UPDATE jobs SET pinned=1 WHERE id=?', (job_id,))

    def voices(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM voices ORDER BY created')]

    def submit(self, request):
        if not isinstance(request, dict) or request.get('kind') not in KINDS | {'command'}:
            raise ValueError('unknown job kind')
        required = {'command': ['argv', 'cwd', 'title'], 'media': ['url'], 'analyze': ['path'], 'dataset': ['analysis', 'speaker', 'clip_ids'],
                    'train': ['dataset', 'name'], 'render': ['voice', 'text'], 'evaluate': ['path', 'expected_text'], 'stitch': ['paths'], 'extract': ['url', 'start', 'end']}
        if any(key not in request for key in required[request['kind']]):
            raise ValueError('missing required job fields')
        request = dict(request)
        if request['kind'] == 'command':
            argv = request['argv']
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\0' in a for a in argv) or not argv[0]:
                raise ValueError('argv must be a nonempty array of strings without NUL bytes')
            cwd = request['cwd']
            if not isinstance(cwd, str) or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
                raise ValueError('cwd must be an existing absolute directory')
            if not isinstance(request['title'], str) or not 1 <= len(request['title']) <= 200:
                raise ValueError('title must contain 1–200 characters')
            # Execution inherits the service environment; no shell interpolation or request env.
            if 'env' in request:
                raise ValueError('per-job environment overrides are not supported')
        dependencies = request.get('dependencies', [])
        if not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies):
            raise ValueError('dependencies must be job IDs')
        if request['kind'] == 'render':
            matches = [v for v in self.voices() if request['voice'] in {v['id'], v['name']}]
            if len(matches) > 1:
                raise ValueError('ambiguous voice name; use its indexed ID')
            if matches:
                request['voice'] = matches[0]['manifest']
        with self.lock:
            rows = self.rows()
            if sum(r['state'] not in TERMINAL for r in rows) >= self.queue_limit:
                raise ValueError('job queue is full; wait before submitting more jobs')
            dependencies = list(request.get('dependencies', []))
            for dependency in dependencies:
                if not any(r['id'] == dependency and r['state'] == 'completed' for r in rows):
                    raise ValueError('dependency must be a completed managed job')
            for row in rows:
                parent = self.jobs / row['id']
                values = list(request.values())
                if isinstance(request.get('paths'), list):
                    values.extend(request['paths'])
                for value in values:
                    if isinstance(value, str) and Path(value).is_absolute() and Path(value).resolve().is_relative_to(parent):
                        if row['state'] != 'completed':
                            raise ValueError('input job is not completed or its artifacts have expired')
                        dependencies.append(row['id'])
            job_id = 'job-' + uuid.uuid4().hex[:16]
            directory = self.jobs / job_id
            directory.mkdir(mode=0o700)
            (directory / 'request.json').write_text(json.dumps(request))
            (directory / 'job.log').touch(mode=0o600)
            now = time.time()
            try:
                with self.db:
                    self.db.execute('INSERT INTO jobs (id,kind,state,created,updated,request,dependencies) VALUES (?,?,?,?,?,?,?)',
                                    (job_id, request['kind'], 'queued', now, now, json.dumps(request), json.dumps(sorted(set(dependencies)))))
            except Exception:
                shutil.rmtree(directory)
                raise
        event('job_queued', job_id=job_id, kind=request['kind'])
        return self.inspect(job_id)

    def update(self, job_id, state, result=None, error=None):
        with self.lock, self.db:
            self.db.execute('UPDATE jobs SET state=?,updated=?,result=?,error=? WHERE id=?',
                            (state, time.time(), json.dumps(result) if result is not None else None, error, job_id))
        event('job_state', job_id=job_id, state=state, error=error)

    def inspect(self, job_id, include_log=True):
        with self.lock:
            row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError('unknown managed job ID')
        data = dict(row)
        directory = self.jobs / job_id
        worker = read_json(directory / 'status.json', {})
        request = json.loads(data.pop('request'))
        data['title'] = request.get('title', data['kind'])
        data['cwd'] = request.get('cwd')
        data['job_id'] = data.pop('id')
        data['directory'] = str(directory)
        data['result'] = json.loads(data['result']) if data['result'] else None
        data['dependencies'] = json.loads(data['dependencies'])
        data['progress'] = read_json(directory / 'progress.json', {})
        if not isinstance(data['progress'], dict):
            data['progress'] = {}
        if data['kind'] == 'extract':
            stage = data['progress'].get('stage')
            if stage in {'downloading_chunk', 'analyzing_chunk'}:
                subdir = 'media' if stage == 'downloading_chunk' else 'analysis'
                data['progress']['detail'] = read_json(directory / subdir / 'progress.json', {})
        data['worker_started_at'] = worker.get('started_at')
        now = time.time()
        heartbeat = read_json(directory / 'heartbeat.json', {})
        data['heartbeat_at'] = heartbeat.get('time')
        data['heartbeat_age_seconds'] = max(0, now - heartbeat['time']) if isinstance(heartbeat.get('time'), (int, float)) else None
        data['monitor_stale'] = data['state'] in {'running', 'cancelling'} and (data['heartbeat_age_seconds'] is None or data['heartbeat_age_seconds'] > 15)
        try:
            data['progress_age_seconds'] = max(0, now - (directory / 'progress.json').stat().st_mtime)
        except FileNotFoundError:
            data['progress_age_seconds'] = None
        data['elapsed_seconds'] = max(0, (now if data['state'] not in TERMINAL else data['updated']) - (worker.get('started_at') or data['created']))
        queued = [r['id'] for r in self.rows() if r['state'] == 'queued']
        data['queue_position'] = queued.index(job_id) + 1 if job_id in queued else None
        if not include_log:
            return data
        try:
            with (directory / 'job.log').open('rb') as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 6000))
                data['log_tail'] = log.read(6000).decode(errors='replace')
        except FileNotFoundError:
            data['log_tail'] = ''
        return data

    def summary(self, job_id):
        data = self.inspect(job_id, include_log=False)
        data.pop('log_tail', None)
        data.pop('result', None)
        return {'id': job_id, **data}

    def cancel(self, job_id):
        with self.lock:
            state = self.inspect(job_id)['state']
            if state not in TERMINAL:
                self.update(job_id, 'cancelled' if state == 'queued' else 'cancelling', error='cancel requested')
        return self.inspect(job_id)

    def cleanup(self, dry_run=True, now=None):
        with self.lock, self.db:
            run_id = self.db.execute('INSERT INTO cleanups (started,dry_run,state) VALUES (?,?,?)',
                                     (time.time(), int(dry_run), 'running')).lastrowid
        try:
            result = self._cleanup(dry_run, now)
        except Exception as exc:
            with self.lock, self.db:
                self.db.execute('UPDATE cleanups SET finished=?,state=?,error=? WHERE id=?',
                                (time.time(), 'failed', str(exc), run_id))
            raise
        with self.lock, self.db:
            self.db.execute('UPDATE cleanups SET finished=?,state=?,result=? WHERE id=?',
                            (time.time(), 'completed', json.dumps(result), run_id))
        return {**result, 'cleanup_id': run_id}

    def cleanups(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM cleanups ORDER BY id DESC LIMIT 100')]

    def _cleanup(self, dry_run=True, now=None):
        now = now or time.time()
        with self.lock:
            rows = {r['id']: r for r in self.rows()}
            protected = {key for key, r in rows.items() if r['pinned'] or r['state'] not in TERMINAL or r['updated'] > now - self.retention}
            pending = list(protected)
            while pending:
                for parent in json.loads(rows[pending.pop()]['dependencies']):
                    if parent in rows and parent not in protected:
                        protected.add(parent)
                        pending.append(parent)
            candidates = [key for key, r in rows.items() if key not in protected and r['state'] in TERMINAL - {'expired'}]
            reclaimed = 0
            for key in candidates:
                directory = self.jobs / key
                if directory.is_symlink():
                    raise ValueError('refusing cleanup of a symlinked job directory')
                reclaimed += self.size(directory)
                if not dry_run:
                    shutil.rmtree(directory, ignore_errors=False) if directory.exists() else None
                    self.update(key, 'expired', error='artifacts removed by retention policy')
                    with self.db:
                        self.db.execute('UPDATE jobs SET bytes=0 WHERE id=?', (key,))
            return {'dry_run': dry_run, 'jobs': candidates, 'bytes': reclaimed, 'protected_jobs': len(protected)}

    @staticmethod
    def size(directory):
        return sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and not p.is_symlink())

    def account(self, job_id):
        size = self.size(self.jobs / job_id)
        with self.lock, self.db:
            self.db.execute('UPDATE jobs SET bytes=? WHERE id=?', (size, job_id))


class JobService:
    def __init__(self, store, max_seconds=7200, min_disk_gb=5, command=None):
        self.store = store
        self.max_seconds = max_seconds
        self.min_disk_gb = min_disk_gb
        self.command = command or (lambda directory: [sys.executable, '-m', 'lm_launcher.voice_guardian', str(directory)])
        self.active = None
        self.stop = threading.Event()
        self.started = time.time()
        self.last_cleanup = 0

    def gpu_available(self):
        with (self.store.root / 'gpu.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                return False

    def tick(self):
        with self.store.lock:
            if self.active:
                job_id, child, started, output, reason = self.active
                state = self.store.inspect(job_id)['state']
                if (state == 'cancelling' or self.stop.is_set() or time.monotonic() - started > self.max_seconds) and reason is None:
                    reason = 'interrupted' if self.stop.is_set() else 'cancelled' if state == 'cancelling' else 'failed'
                    self.active = (job_id, child, started, output, reason)
                    child.stdin.close()  # Guardian terminates only its owned process group.
                code = child.poll()
                if code is not None:
                    output.close()
                    status = read_json(self.store.jobs / job_id / 'status.json', {})
                    if reason:
                        self.store.update(job_id, reason, error='service shutdown' if reason == 'interrupted' else 'cancelled by user' if reason == 'cancelled' else 'job exceeded wall-clock deadline')
                    elif code == 0 and status.get('state') == 'completed':
                        self.store.update(job_id, 'completed', result=status.get('result'))
                        if self.store.inspect(job_id)['kind'] == 'train':
                            self.store.index_voice(job_id, self.store.jobs / job_id / 'trained-voice.json')
                    else:
                        self.store.update(job_id, 'failed', error=status.get('error', f'worker exited with status {code}'))
                    if not child.stdin.closed:
                        child.stdin.close()
                    self.store.account(job_id)
                    self.active = None
                return
            if self.stop.is_set():
                return
            if time.time() - self.last_cleanup > 3600:
                try:
                    result = self.store.cleanup(dry_run=False)
                    event('cleanup', **result)
                except OSError as exc:
                    # A protected/read-only artifact must not take down job admission.
                    event('cleanup_failed', error=str(exc))
                self.last_cleanup = time.time()
            queued = [r for r in self.store.rows() if r['state'] == 'queued']
            if not queued:
                return
            row = queued[0]
            if row['kind'] in GPU_KINDS and not self.gpu_available():
                return
            if shutil.disk_usage(self.store.root).free < self.min_disk_gb * 1024**3:
                self.store.update(row['id'], 'failed', error='insufficient free disk space')
                return
            directory = self.store.jobs / row['id']
            output = (directory / 'job.log').open('ab', buffering=0)
            self.store.update(row['id'], 'running')
            try:
                env = {**os.environ, 'LM_VOICE_WORKBENCH_ROOT': str(self.store.root)}
                child = subprocess.Popen(self.command(directory), cwd=ROOT, stdin=subprocess.PIPE, stdout=output,
                                         stderr=subprocess.STDOUT, start_new_session=True, env=env)
            except Exception as exc:
                output.close()
                self.store.update(row['id'], 'failed', error=f'worker launch failed: {exc}')
                return
            self.active = (row['id'], child, time.monotonic(), output, None)

    def health(self):
        counts = Counter(r['state'] for r in self.store.rows())
        return {'status': 'stopping' if self.stop.is_set() else 'ok', 'uptime_seconds': round(time.time() - self.started),
                'jobs': dict(counts), 'active_job': self.active[0] if self.active else None,
                'active_progress': self.store.inspect(self.active[0])['progress'] if self.active else None,
                'indexed_voices': len(self.store.voices()), 'free_disk_bytes': shutil.disk_usage(self.store.root).free,
                'managed_artifact_bytes': sum(r['bytes'] for r in self.store.rows()),
                'last_cleanup': next(iter(self.store.cleanups()), None)}


def handler(service, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, value, content_type='application/json'):
            data = (json.dumps(value) if content_type == 'application/json' else value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.route()

        def do_POST(self):
            self.route()

        def route(self):
            self.connection.settimeout(10)
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.respond(401, {'error': 'unauthorized'})
                return
            path = urlsplit(self.path).path
            try:
                body = {}
                if self.command == 'POST':
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 1024 * 1024:
                        self.respond(413, {'error': 'request must contain at most 1 MiB'})
                        return
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise ValueError('request must be an object')
                if self.command == 'GET' and path == '/health':
                    self.respond(200, service.health())
                elif self.command == 'GET' and path == '/metrics':
                    health = service.health()
                    lines = [f'local_jobs{{state="{state}"}} {count}' for state, count in health['jobs'].items()]
                    lines += [f'voice_jobs{{state="{state}"}} {count}' for state, count in health['jobs'].items()]
                    lines += [f'voice_{key} {health[key]}' for key in ('uptime_seconds', 'indexed_voices', 'free_disk_bytes', 'managed_artifact_bytes')]
                    self.respond(200, '\n'.join(lines) + '\n', 'text/plain; version=0.0.4')
                elif self.command == 'GET' and path == '/voices':
                    self.respond(200, {'voices': service.store.voices()})
                elif self.command == 'GET' and path == '/cleanup':
                    self.respond(200, {'cleanups': service.store.cleanups()})
                elif self.command == 'GET' and path == '/jobs':
                    self.respond(200, {'jobs': [service.store.summary(r['id']) for r in service.store.rows()[-200:]]})
                elif self.command == 'POST' and path == '/jobs':
                    if service.stop.is_set():
                        self.respond(503, {'error': 'service is stopping'})
                    else:
                        self.respond(202, service.store.submit(body))
                elif self.command == 'POST' and path == '/cleanup':
                    if not isinstance(body.get('dry_run', True), bool):
                        raise ValueError('dry_run must be boolean')
                    self.respond(200, service.store.cleanup(body.get('dry_run', True)))
                elif path.startswith('/jobs/'):
                    parts = path.strip('/').split('/')
                    if self.command == 'GET' and len(parts) == 2:
                        self.respond(200, service.store.inspect(parts[1]))
                    elif self.command == 'POST' and len(parts) == 3 and parts[2] == 'cancel':
                        self.respond(200, service.store.cancel(parts[1]))
                    else:
                        self.respond(404, {'error': 'unknown endpoint'})
                else:
                    self.respond(404, {'error': 'unknown endpoint'})
            except KeyError as exc:
                self.respond(404, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                LOG.exception('request failed')
                self.respond(500, {'error': 'internal service error; inspect service log'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--port', type=int, default=8093)
    parser.add_argument('--retention-days', type=float, default=7)
    parser.add_argument('--max-seconds', type=float, default=7200)
    args = parser.parse_args()
    if args.retention_days <= 0 or args.max_seconds <= 0:
        parser.error('retention and deadline must be positive')
    os.umask(0o077)
    args.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.root / 'service.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, 'voice job service already owns this store\n')
        LOG.setLevel(logging.INFO)
        LOG.addHandler(logging.StreamHandler())
        LOG.addHandler(RotatingFileHandler(args.root / 'service.jsonl', maxBytes=4 * 1024**2, backupCount=3))
        token_path = args.root / 'token'
        if not token_path.exists():
            token_path.write_text(secrets.token_urlsafe(32))
        token_path.chmod(0o600)
        store = JobStore(args.root, args.retention_days)
        service = JobService(store, max_seconds=args.max_seconds)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(service, token_path.read_text().strip()))
        store.recover()
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, lambda *_: service.stop.set())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        event('service_started', port=args.port)
        try:
            while not service.stop.is_set() or service.active:
                service.tick()
                time.sleep(.2)
        finally:
            service.stop.set()
            while service.active:
                service.tick()
                time.sleep(.1)
            server.shutdown()
            server.server_close()
            store.db.close()
            event('service_stopped')


if __name__ == '__main__':
    main()

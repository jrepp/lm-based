"""Exercise real owned subprocesses without models or installed live services."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from lm_launcher.job_service import JobStore, JobService
from lm_launcher.job_progress import report


class CommandJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root)
        self.service = JobService(self.store, min_disk_gb=0)

    def tearDown(self):
        self.service.stop.set()
        self.finish()
        self.store.db.close()
        self.temp.cleanup()

    def submit(self, code, **fields):
        return self.store.submit({'kind': 'command', 'argv': [sys.executable, '-c', code],
                                  'cwd': str(self.root), 'title': 'Test command', **fields})['job_id']

    def finish(self):
        deadline = time.monotonic() + 10
        while self.service.active and time.monotonic() < deadline:
            self.service.tick()
            time.sleep(.02)
        self.assertIsNone(self.service.active)

    def test_command_progress_cwd_logs_and_exit_status(self):
        job = self.submit("import os,json,pathlib; print('task output'); pathlib.Path('cwd-marker').touch(); pathlib.Path(os.environ['LM_JOB_PROGRESS_FILE']).write_text(json.dumps({'stage':'done','completed':3,'total':3}))")
        self.assertEqual(self.store.inspect(job)['queue_position'], 1)
        self.service.tick()
        self.finish()
        value = self.store.inspect(job)
        self.assertEqual(value['state'], 'completed')
        self.assertEqual(value['result']['exit_code'], 0)
        self.assertEqual(value['progress']['completed'], 3)
        self.assertIn('task output', value['log_tail'])
        self.assertTrue((self.root / 'cwd-marker').exists())
        self.assertIsNotNone(value['worker_started_at'])
        self.assertIsNotNone(value['progress_age_seconds'])
        self.assertGreaterEqual(value['elapsed_seconds'], 0)
        self.assertEqual(self.store.summary(job)['title'], 'Test command')
        self.assertNotIn('log_tail', self.store.summary(job))

    def test_nonzero_and_missing_executable_fail_durably(self):
        for argv in ([sys.executable, '-c', 'raise SystemExit(7)'], ['/no/such/command']):
            job = self.submit('', argv=argv)
            self.service.tick()
            self.finish()
            self.assertEqual(self.store.inspect(job)['state'], 'failed')
            self.assertTrue(self.store.inspect(job)['error'])

    def test_cancellation_and_timeout(self):
        for cancel in (True, False):
            job = self.submit('import time; time.sleep(60)')
            self.service.max_seconds = 10 if cancel else .1
            self.service.tick()
            if cancel:
                self.store.cancel(job)
            self.finish()
            self.assertEqual(self.store.inspect(job)['state'], 'cancelled' if cancel else 'failed')

    def test_heartbeat_is_independent_of_progress(self):
        job = self.submit('import time; time.sleep(60)')
        self.service.tick()
        deadline = time.monotonic() + 5
        while not self.store.inspect(job)['heartbeat_at'] and time.monotonic() < deadline:
            time.sleep(.02)
        value = self.store.inspect(job)
        self.assertFalse(value['monitor_stale'])
        self.assertEqual(value['progress'], {})
        self.assertIsNone(value['progress_age_seconds'])
        self.store.cancel(job)
        self.finish()

    def test_validation_dependencies_and_retention(self):
        for fields in ({'argv': []}, {'argv': ['echo', 3]}, {'cwd': 'relative'}, {'title': ''}, {'env': {}}, {'dependencies': ['missing']}):
            with self.assertRaises(ValueError):
                self.submit('', **fields)
        parent = self.submit('')
        with self.assertRaises(ValueError):
            self.submit('', dependencies=[parent])
        self.store.update(parent, 'completed')
        child = self.submit('', dependencies=[parent])
        self.assertEqual(self.store.inspect(child)['dependencies'], [parent])
        self.assertEqual(self.store.cleanup(now=time.time() + 10 * 86400)['jobs'], [])

    def test_http_command_submission_and_monitoring(self):
        from http.server import ThreadingHTTPServer
        import threading
        from urllib.request import Request, urlopen
        from lm_launcher.job_service import handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.service, 'test-token'))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()

        def call(route, body=None):
            request = Request(f'http://127.0.0.1:{server.server_port}' + route,
                              data=json.dumps(body).encode() if body is not None else None,
                              headers={'Authorization': 'Bearer test-token'})
            with urlopen(request, timeout=3) as response:
                return json.load(response)

        try:
            job = call('/jobs', {'kind': 'command', 'title': 'API task',
                                'argv': [sys.executable, '-c', 'print("done")'], 'cwd': str(self.root)})
            listed = call('/jobs')['jobs'][0]
            self.assertEqual(listed['id'], job['job_id'])
            self.assertEqual(listed['queue_position'], 1)
            self.assertEqual(listed['title'], 'API task')
            self.assertNotIn('log_tail', listed)
            self.service.tick()
            self.finish()
            self.assertEqual(call('/jobs/' + job['job_id'])['state'], 'completed')
            self.assertEqual(call('/health')['jobs']['completed'], 1)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_progress_helper(self):
        target = self.root / 'progress.json'
        with patch.dict(os.environ, {'LM_JOB_PROGRESS_FILE': str(target)}):
            report('testing', 2, 4, 'halfway')
            self.assertEqual(json.loads(target.read_text())['percent'], 50)
            for completed, total in ((5, 4), (-1, 4), (float('nan'), 4)):
                with self.assertRaises(ValueError):
                    report('bad', completed, total)
        self.assertEqual(list(self.root.glob('.progress-*')), [])


if __name__ == '__main__':
    unittest.main()

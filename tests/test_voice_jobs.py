import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from lm_launcher.voice_jobs import JobStore, JobService
from lm_launcher.voice_runtime import runtime_command


class VoiceJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root, retention_days=1)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def submit(self):
        return self.store.submit({'kind': 'analyze', 'path': '/tmp/input.wav'})['job_id']

    def test_recovery_never_relaunches_interrupted_work(self):
        running = self.submit()
        queued = self.submit()
        self.store.update(running, 'running')
        self.store.recover()
        self.assertEqual(self.store.inspect(running)['state'], 'interrupted')
        self.assertEqual(self.store.inspect(queued)['state'], 'queued')
        self.assertEqual(self.store.cancel(queued)['state'], 'cancelled')

    def test_retention_protects_voice_dependency_chain_and_external_files(self):
        analysis = self.submit()
        self.store.update(analysis, 'completed')
        data = self.store.submit({'kind': 'dataset', 'analysis': str(self.store.jobs / analysis / 'analysis.json'), 'speaker': 'one', 'clip_ids': ['clip_1']})['job_id']
        self.store.update(data, 'completed')
        trained = self.store.submit({'kind': 'train', 'dataset': str(self.store.jobs / data / 'dataset.json'), 'name': 'one'})['job_id']
        self.store.update(trained, 'completed')
        model = self.store.jobs / trained / 'checkpoint'
        model.mkdir()
        manifest = model.parent / 'trained-voice.json'
        manifest.write_text(json.dumps({'model': str(model), 'name': 'one'}))
        self.store.index_voice(trained, manifest)
        unneeded = self.submit()
        self.store.update(unneeded, 'failed', error='test')
        legacy = self.store.jobs / 'job-legacy'
        legacy.mkdir()
        future = time.time() + 2 * 86400
        self.assertEqual(self.store.cleanup(now=future)['jobs'], [unneeded])
        self.assertTrue((self.store.jobs / unneeded).exists())
        self.store.cleanup(False, now=future)
        self.assertEqual(self.store.inspect(unneeded)['state'], 'expired')
        self.assertTrue(legacy.exists())
        self.assertTrue(model.exists())
        self.assertTrue((self.store.jobs / analysis).exists())
        self.assertEqual(self.store.cleanups()[0]['state'], 'completed')
        render = self.store.submit({'kind': 'render', 'voice': trained, 'text': 'Hello'})
        self.assertEqual(render['dependencies'], [trained])

    def test_stitch_tracks_all_input_jobs_for_retention(self):
        first, second = self.submit(), self.submit()
        self.store.update(first, 'completed')
        self.store.update(second, 'completed')
        mixed = self.store.submit({'kind': 'stitch', 'paths': [str(self.store.jobs / first / 'a.wav'), str(self.store.jobs / second / 'b.wav')]})
        self.assertEqual(set(mixed['dependencies']), {first, second})
        self.assertNotIn('mlx-audio==0.6.6', runtime_command('stitch', self.root))
        self.assertIn('yt-dlp[default]==2026.10.26', runtime_command('extract', self.root))
        self.assertIn('mlx-whisper==0.4.3', runtime_command('extract', self.root))

    def test_launch_failure_and_queue_capacity_are_durable(self):
        job = self.submit()
        service = JobService(self.store, min_disk_gb=0, command=lambda _: ['/no/such/program'])
        with patch.object(service, 'gpu_available', return_value=True):
            service.tick()
        self.assertEqual(self.store.inspect(job)['state'], 'failed')
        self.store.queue_limit = 1
        self.submit()
        with self.assertRaisesRegex(ValueError, 'full'):
            self.submit()

    def test_worker_completion_and_shutdown_via_control_pipe(self):
        job = self.submit()
        code = "import pathlib,json,sys; p=pathlib.Path(sys.argv[1]); (p/'status.json').write_text(json.dumps({'state':'completed','result':{'ok':True}}))"
        service = JobService(self.store, min_disk_gb=0, command=lambda p: [sys.executable, '-c', code, str(p)])
        with patch.object(service, 'gpu_available', return_value=True):
            service.tick()
            deadline = time.time() + 5
            while service.active and time.time() < deadline:
                service.tick()
                time.sleep(.01)
        self.assertEqual(self.store.inspect(job)['result'], {'ok': True})
        other = self.submit()
        code = "import sys; sys.stdin.buffer.read()"
        service.command = lambda _: [sys.executable, '-c', code]
        with patch.object(service, 'gpu_available', return_value=True):
            service.tick()
        service.stop.set()
        deadline = time.time() + 5
        while service.active and time.time() < deadline:
            service.tick()
            time.sleep(.01)
        self.assertIsNone(service.active)
        self.assertEqual(self.store.inspect(other)['state'], 'interrupted')

    def test_guardian_reaps_worker_on_parent_pipe_eof(self):
        marker = self.root / 'worker.pid'
        worker = 'import os,time,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)'
        wrapper = 'from lm_launcher.voice_guardian import supervise; import sys; sys.exit(supervise(sys.argv[1:], grace=.1))'
        guardian = subprocess.Popen([sys.executable, '-c', wrapper, sys.executable, '-c', worker, str(marker)], stdin=subprocess.PIPE)
        try:
            deadline = time.time() + 5
            while not marker.exists() and time.time() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            pid = int(marker.read_text())
            guardian.stdin.close()
            self.assertEqual(guardian.wait(timeout=5), 130)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            if guardian.poll() is None:
                guardian.terminate()
                guardian.wait(timeout=5)

    def test_cleanup_failure_is_recorded_and_does_not_stop_service(self):
        job = self.submit()
        self.store.update(job, 'failed')
        with patch('lm_launcher.voice_jobs.shutil.rmtree', side_effect=PermissionError('read-only')):
            with self.assertRaises(PermissionError):
                self.store.cleanup(False, now=time.time() + 2 * 86400)
        self.assertEqual(self.store.cleanups()[0]['state'], 'failed')
        service = JobService(self.store)
        with patch.object(self.store, 'cleanup', side_effect=PermissionError('read-only')):
            service.tick()
        self.assertFalse(service.stop.is_set())

    def test_runtime_separates_legacy_trainer(self):
        args = runtime_command('train', self.root)
        self.assertIn('mlx-audio==0.3.1', args)
        self.assertIn('3.12', args)
        self.assertIn('mlx-whisper==0.4.3', runtime_command('analyze', self.root))
        with self.assertRaises(ValueError):
            runtime_command('shell', self.root)

class VoiceHttpTests(unittest.TestCase):
    def test_auth_and_api_contract(self):
        from http.server import ThreadingHTTPServer
        import threading
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from lm_launcher.voice_jobs import handler
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            service = JobService(store)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(service, 'test-token'))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            def call(path, body=None):
                request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                  headers={'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'})
                with urlopen(request, timeout=3) as response:
                    return json.load(response)
            try:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + '/health', timeout=3)
                self.assertEqual(error.exception.code, 401)
                error.exception.close()
                job = call('/jobs', {'kind': 'analyze', 'path': '/tmp/audio.wav'})
                self.assertEqual(job['state'], 'queued')
                self.assertEqual(call('/jobs/' + job['job_id'] + '/cancel', {})['state'], 'cancelled')
                self.assertTrue(call('/cleanup', {})['dry_run'])
                self.assertEqual(call('/health')['jobs']['cancelled'], 1)
                self.assertEqual(len(call('/jobs')['jobs']), 1)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
                store.db.close()


if __name__ == '__main__':
    unittest.main()

"""Offline lifecycle checks; launches only local Python fixtures on Windows."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller as C
import processes as P
from test_controller import FakeAdapter, FakeRunner


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = C.Controller(self.root / 'state.db', adapters={'fake': FakeAdapter()})
        self.jid = self.c.add('fixture', 'builder', 'fake', str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_recovery_refuses_alive_unknown_and_is_atomic(self):
        self.c.claim()
        for state in ('alive', 'unknown'):
            with patch.object(P, 'owner_state', return_value=state):
                with self.assertRaises(C.ControllerError):
                    self.c.recover()
            self.assertEqual(self.c.get(self.jid).status, 'running')
        with patch.object(P, 'owner_state', return_value='dead'):
            self.assertEqual(self.c.recover(), [self.jid])
        self.assertEqual(self.c.get(self.jid).status, 'interrupted')
        self.assertTrue(self.c.paused_reason())
        self.c.resume()
        self.assertIsNone(self.c.claim())
        self.assertEqual(self.c.recover(), [])

    def test_migration_preserves_legacy_job_and_refuses_unknown_owner(self):
        old = self.root / 'old.db'
        with sqlite3.connect(old) as db:
            db.execute('CREATE TABLE jobs (id INTEGER PRIMARY KEY, task TEXT, kind TEXT, '
                       'provider TEXT, worktree TEXT, status TEXT, started_at REAL, '
                       'finished_at REAL, exit_code INTEGER, output TEXT)')
            db.execute("INSERT INTO jobs (id, status) VALUES (1, 'running')")
        db.close()
        migrated = C.Controller(old)
        C.Controller(old)  # migration is idempotent
        with self.assertRaises(C.ControllerError):
            migrated.recover()
        self.assertEqual(migrated.get(1).status, 'running')

    def test_mixed_owners_refuse_whole_recovery(self):
        self.c.claim()
        self.c.add('second', 'builder', 'fake', str(self.root / 'other'))
        self.c.claim()
        with patch.object(P, 'owner_state', side_effect=['dead', 'unknown']):
            with self.assertRaises(C.ControllerError):
                self.c.recover()
        self.assertEqual(self.c.counts(), {'running': 2})

    def test_production_adapters_stay_disabled(self):
        self.assertTrue(all(not a.live_enabled for a in C.ADAPTERS.values()))

    def test_launch_and_argv_failures_settle(self):
        for build_failure in (False, True):
            self.c.resume()
            if build_failure:
                jid = self.c.add('second', 'builder', 'fake', str(self.root))
                context = patch.object(self.c.adapters['fake'], 'build_argv', side_effect=OSError('argv failed'))
            else:
                jid = self.jid
                context = patch.object(P, 'run', side_effect=OSError('launch failed'))
            with context:
                runner = FakeRunner(lambda *args: (_ for _ in ()).throw(OSError('launch failed')))
                self.c.run(execute=True, runner=runner)
            self.assertEqual(self.c.get(jid).status, 'failed')
            self.assertTrue(self.c.paused_reason())

    def test_unsupported_platform_fails_closed(self):
        with patch.object(P.os, 'name', 'unsupported'):
            with self.assertRaisesRegex(OSError, 'containment unavailable'):
                P.run([sys.executable, '-c', 'raise Exception()'], cwd=str(self.root), timeout=1)

    def test_native_launch_failure_settles_claim(self):
        with patch.object(self.c.adapters['fake'], 'build_argv',
                          return_value=[str(self.root / 'nonexistent-worker.exe')]):
            self.c.run(execute=True, timeout=1)
        self.assertEqual(self.c.get(self.jid).status, 'failed')
        self.assertTrue(self.c.paused_reason())

    @unittest.skipUnless(os.name == 'nt', 'Windows native identity')
    def test_native_identity_living_dead_and_unverifiable(self):
        self.assertEqual(P.owner_state(*P.identity()), 'alive')
        host, pid, birth = P.identity()
        self.assertEqual(P.owner_state(host, pid, str(int(birth) + 1)), 'dead')
        self.assertEqual(P.owner_state(None, None, None), 'unknown')
        self.assertEqual(P.owner_state('other-host', 1, '1'), 'unknown')
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        self.assertEqual(P.owner_state(P.identity()[0], child.pid, '1'), 'dead')


@unittest.skipUnless(os.name == 'nt', 'Windows Job Objects required')
class ContainmentTests(unittest.TestCase):
    def test_controller_interruption_pauses_and_cleans_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker, identity = self.fixture(root)
            adapter = FakeAdapter()
            controller = C.Controller(root / 'state.db', adapters={'fake': adapter})
            jid = controller.add('fixture', 'builder', 'fake', tmp)

            def interrupt_after_child_starts(futures):
                self.wait_file(identity)
                raise KeyboardInterrupt()

            with patch.object(adapter, 'build_argv', return_value=[sys.executable, str(worker)]):
                with patch.object(C, 'as_completed', side_effect=interrupt_after_child_starts):
                    with self.assertRaises(KeyboardInterrupt):
                        controller.run(execute=True, timeout=15)
            self.assertEqual(controller.get(jid).status, 'interrupted')
            self.assertTrue(controller.paused_reason())
            self.assert_dead(self.wait_file(identity))

    def test_assignment_failure_never_executes_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'executed'
            with patch.object(P.k, 'AssignProcessToJobObject', return_value=False):
                with self.assertRaises(OSError):
                    P.run([sys.executable, '-c',
                           'from pathlib import Path; Path(%r).touch()' % str(marker)],
                          cwd=tmp, timeout=3)
            self.assertFalse(marker.exists())

    def test_cancellation_cleans_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker, identity = self.fixture(root)
            cancel = threading.Event()
            errors = []

            def run():
                try:
                    P.run([sys.executable, str(worker)], cwd=tmp,
                          timeout=15, cancel_event=cancel)
                except InterruptedError:
                    errors.append('interrupted')

            thread = threading.Thread(target=run)
            thread.start()
            try:
                child_identity = self.wait_file(identity)
            finally:
                cancel.set()
                thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, ['interrupted'])
            self.assert_dead(child_identity)

    def wait_file(self, path, parent=None):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except (ValueError, OSError):
                    pass
            if parent is not None and parent.poll() is not None:
                self.fail('fixture parent exited before child readiness')
            time.sleep(.02)
        self.fail('fixture readiness timeout')

    def assert_dead(self, identity):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if P.owner_state(*identity) == 'dead':
                return
            time.sleep(.02)
        self.fail('contained descendant survived')

    def fixture(self, root):
        child = root / 'child.py'
        identity = root / 'identity.json'
        child.write_text('import sys,time,json\n'
                         'sys.path.insert(0, %r)\nimport processes as P\n' % str(Path(P.__file__).parent)
                         + 'from pathlib import Path\nPath(%r).write_text(json.dumps(P.identity()))\ntime.sleep(60)\n' % str(identity))
        worker = root / 'worker.py'
        worker.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,%r])\ntime.sleep(60)\n' % str(child))
        return worker, identity

    def test_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker, identity = self.fixture(root)
            with self.assertRaises(subprocess.TimeoutExpired):
                P.run([sys.executable, str(worker)], cwd=tmp, timeout=3)
            self.assert_dead(self.wait_file(identity))

    def test_success_cleans_remaining_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker, identity = self.fixture(root)
            worker.write_text(worker.read_text().replace('time.sleep(60)', 'time.sleep(2)'))
            result = P.run([sys.executable, str(worker)], cwd=tmp, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assert_dead(self.wait_file(identity))

    def test_parent_termination_cleans_tree_and_allows_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker, identity = self.fixture(root)
            harness = root / 'parent.py'
            db = root / 'state.db'
            harness.write_text(
                'import sys\nsys.path.insert(0,%r)\nimport controller as C\n' % str(Path(C.__file__).parent)
                + 'class Fixture(C.Adapter):\n live_enabled=True\n'
                + ' def build_argv(self,*args): return [sys.executable,%r]\n' % str(worker)
                + 'c=C.Controller(%r,adapters={"fixture":Fixture()})\n' % str(db)
                + 'c.add("local fixture","builder","fixture",%r)\nc.run(execute=True)\n' % tmp)
            parent = subprocess.Popen([sys.executable, str(harness)])
            try:
                child_identity = self.wait_file(identity, parent)
                c = C.Controller(db)
                with self.assertRaises(C.ControllerError):
                    c.recover()
                parent.terminate()  # only our exact owned fixture process
                parent.wait(10)
                self.assert_dead(child_identity)
                self.assertEqual(c.recover(), [1])
                self.assertEqual(c.get(1).status, 'interrupted')
                self.assertTrue(c.paused_reason())
            finally:
                if parent.poll() is None:
                    parent.terminate()
                    parent.wait(10)


if __name__ == '__main__':
    unittest.main()

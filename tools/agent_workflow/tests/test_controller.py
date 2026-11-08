"""Offline tests for the local agent-workflow controller.

Standard library only (unittest). Uses fake workers/adapters — no real
AI CLI is ever launched, nothing is installed, no network access.

Run from the repo root:
    python tools\\agent_workflow\\tests\\test_controller.py -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import controller as C


class FakeAdapter(C.Adapter):
    """Test-only live-enabled adapter (production adapters all stay
    live-disabled pending end-to-end validation)."""
    provider = "fake"
    live_enabled = True
    live_disabled_reason = ""

    def build_argv(self, job, instructions, out_dir):
        return ["fake-worker", "--job", str(job.id), job.task]


class FakeRunner:
    """Stands in for subprocess.run; records every call."""

    def __init__(self, behavior=None):
        self.calls = []
        self.behavior = behavior

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.behavior is not None:
            return self.behavior(argv, kw)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.adapters = {
            "fake": FakeAdapter(),
            "codex": C.CodexAdapter(executable=str(Path(self.tmp.name) / "fake-codex.exe")),
            "opencode": C.OpenCodeAdapter(),
            "claude": C.ClaudeAdapter(),
        }
        self.c = C.Controller(Path(self.tmp.name) / "state.db", adapters=self.adapters)
        self.wt = str(Path(self.tmp.name) / "wt")
        os.makedirs(self.wt, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def add_job(self, kind="builder", provider="fake", task="t", worktree=None):
        return self.c.add(task, kind, provider, worktree or self.wt)

    def new_wt(self, name):
        p = str(Path(self.tmp.name) / name)
        os.makedirs(p, exist_ok=True)
        return p

    def running_count(self):
        return self.c.counts().get("running", 0)

    # -- dry run is a read-only preview ------------------------------------

    def test_dry_run_preview_does_not_change_state(self):
        for i in range(3):
            self.add_job(task="t%d" % i)
        runner = FakeRunner()
        ids = self.c.run(execute=False, runner=runner)
        self.assertEqual(ids, [1, 2, 3])
        self.assertEqual(runner.calls, [], "preview must launch nothing")
        self.assertEqual(self.c.counts(), {"pending": 3},
                         "preview must not change queue state")
        # a second preview sees the same pending jobs
        self.assertEqual(self.c.run(execute=False, runner=runner), [1, 2, 3])
        self.assertEqual(self.c.counts(), {"pending": 3})

    # -- limits and state location ------------------------------------------

    def test_ceiling_cannot_be_raised_by_override(self):
        with self.assertRaises(C.ControllerError) as ctx:
            C.Controller(Path(self.tmp.name) / "x.db", max_jobs=3, ceiling=5)
        self.assertIn("hard ceiling", str(ctx.exception))
        # ceiling == 4 is still allowed
        C.Controller(Path(self.tmp.name) / "y.db", max_jobs=3, ceiling=4,
                     adapters=self.adapters)

    def test_state_and_outputs_outside_tracked_source(self):
        self.assertFalse(C.DEFAULT_DB.is_relative_to(C.REPO_ROOT),
                         "default DB must live outside the repo")
        self.assertIn(os.environ.get("LOCALAPPDATA", ""), str(C.DEFAULT_DB))
        # state dir is created for a fresh path
        fresh = Path(self.tmp.name) / "newstate" / "state.db"
        C.Controller(fresh, adapters=self.adapters)
        self.assertTrue(fresh.parent.is_dir())
        # builder output files go to the state dir, not the worktree
        job = C.Job(id=7, task="t", kind="builder", provider="codex",
                    worktree=self.wt, status="running")
        out_dir = Path(self.tmp.name) / "out"
        argv = self.adapters["codex"].build_argv(job, Path("AGENTS.md"), out_dir)
        o = argv[argv.index("-o") + 1]
        self.assertEqual(o, str(out_dir / "result-7.txt"))
        self.assertTrue(o.startswith(str(out_dir)))

    # -- Codex executable resolution (Windows shims) -------------------------

    def test_codex_executable_resolved_not_ps1(self):
        exe = shutil.which("codex")
        if exe is None:
            self.skipTest("codex not on PATH in this environment")
        self.assertFalse(exe.lower().endswith(".ps1"),
                         "a .ps1 shim cannot run via subprocess shell=False")
        self.assertTrue(os.path.exists(exe))
        job = C.Job(id=1, task="t", kind="builder", provider="codex",
                    worktree=self.wt, status="running")
        argv = C.CodexAdapter().build_argv(job, Path("AGENTS.md"), self.wt)
        self.assertTrue(Path(argv[0]).is_file())
        self.assertFalse(argv[0].lower().endswith((".ps1", ".cmd", ".bat")))
        # a .ps1 resolution must be refused
        with self.assertRaises(C.ControllerError):
            C.CodexAdapter(executable="C:\\x\\codex.ps1").build_argv(
                job, Path("AGENTS.md"), self.wt)

    # -- claim rules ----------------------------------------------------------

    def test_shared_worktree_rejected_in_claim(self):
        wt1 = self.new_wt("w1")
        wt2 = self.new_wt("w2")
        j1 = self.add_job(task="a", worktree=wt1)
        j2 = self.add_job(task="b", worktree=wt1)  # same resolved worktree
        j3 = self.add_job(task="c", worktree=wt2)
        with self.c._db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (j1,))
        self.assertEqual(self.c.claim(), j3,
                         "a different worktree is claimable, not the shared one")
        with self.c._db() as db:
            db.execute("UPDATE jobs SET status='done' WHERE id=?", (j1,))
        self.assertEqual(self.c.claim(), j2,
                         "shared worktree becomes claimable once it is free")

    def test_concurrent_claims_respect_cap(self):
        for i in range(6):
            self.add_job(task="t%d" % i, worktree=self.new_wt("w%d" % i))
        release = threading.Event()

        def blocking(argv, kw):
            release.wait(15)
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        runner = FakeRunner(blocking)
        errors = []

        def do_run():
            try:
                self.c.run(execute=True, runner=runner)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=do_run)
        t.start()
        deadline = time.time() + 15
        while time.time() < deadline and self.running_count() < 2:
            time.sleep(0.02)
        self.assertEqual(self.running_count(), 2,
                         "cap: exactly two managed jobs may run")
        deadline = time.time() + 15
        while time.time() < deadline and len(runner.calls) < 2:
            time.sleep(0.02)
        self.assertEqual(len(runner.calls), 2)
        for _ in range(40):  # while blocked, never exceed the cap
            self.assertLessEqual(self.running_count(), 2)
            time.sleep(0.01)
        release.set()
        t.join(20)
        self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.running_count(), 0)
        self.assertEqual(len(runner.calls), 2, "one pass, no retries")
        self.assertEqual(self.c.counts().get("pending", 0), 4)

    def test_atomic_concurrent_claims(self):
        for i in range(8):
            self.add_job(task="t%d" % i, worktree=self.new_wt("w%d" % i))
        results, lock = [], threading.Lock()

        def worker():
            jid = self.c.claim()
            with lock:
                results.append(jid)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)
        claimed = [r for r in results if r is not None]
        self.assertEqual(len(claimed), 2, "cap blocks the rest")
        self.assertEqual(len(set(claimed)), 2, "no double-claim")

    def test_hard_ceiling(self):
        for i in range(4):
            self.add_job(task="t%d" % i, worktree=self.new_wt("w%d" % i))
        with self.c._db() as db:
            db.execute("UPDATE jobs SET status='running'")
        self.assertIsNone(self.c.claim(), "ceiling of four must block claims")

    # -- live dispatch is disabled: pause + return to queue -------------------

    def test_live_run_pauses_on_disabled_adapter_and_returns_ids(self):
        self.add_job(task="x", provider="codex")
        runner = FakeRunner()
        ids = self.c.run(execute=True, runner=runner)
        self.assertEqual(ids, [], "nothing terminal was processed")
        self.assertEqual(self.c.get(1).status, "pending",
                         "refused job is returned to the queue")
        self.assertIn("live dispatch disabled", self.c.paused_reason())
        self.assertEqual(runner.calls, [], "disabled adapter launches nothing")

    def test_opencode_dry_run_still_works_while_live_disabled(self):
        self.add_job(task="x", provider="opencode")
        runner = FakeRunner()
        ids = self.c.run(execute=False, runner=runner)
        self.assertEqual(ids, [1])
        self.assertEqual(self.c.counts(), {"pending": 1})
        self.assertEqual(runner.calls, [])

    # -- failure / timeout handling (via the test-only live adapter) ---------

    def test_failure_pauses_and_no_retry(self):
        self.add_job(task="boom", worktree=self.new_wt("w1"))
        runner = FakeRunner(
            lambda argv, kw: subprocess.CompletedProcess(argv, 1,
                                                         stdout="", stderr="boom"))
        self.c.run(execute=True, runner=runner)
        self.assertEqual(self.c.get(1).status, "failed")
        self.assertTrue(self.c.paused_reason())
        self.assertEqual(len(runner.calls), 1)

        # paused: nothing new is claimed
        self.add_job(task="second", worktree=self.new_wt("w2"))
        self.c.run(execute=True, runner=runner)
        self.assertEqual(len(runner.calls), 1, "pause blocks dispatch")
        self.assertEqual(self.c.get(2).status, "pending")
        self.assertEqual(self.c.get(1).status, "failed", "failed job not retried")

        # Jacob resumes; only the pending job runs
        self.c.resume()
        self.c.run(execute=True, runner=runner)
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(self.c.get(1).status, "failed")

    def test_failure_status_and_pause_single_transaction(self):
        # A reader must never observe the job 'failed' without the pause
        # already visible (the two-step finish-then-pause regression).
        c = C.Controller(Path(self.tmp.name) / "race.db", max_jobs=1,
                         adapters=self.adapters)
        j1 = c.add("a", "builder", "fake", self.new_wt("r1"))
        c.add("b", "builder", "fake", self.new_wt("r2"))
        self.assertEqual(c.claim(), j1)
        violations = []
        stop = threading.Event()

        def spinner():
            while not stop.is_set():
                if c.get(j1).status == "failed" and not c.paused_reason():
                    violations.append(1)

        t = threading.Thread(target=spinner)
        t.start()
        c.settle(j1, "failed", 1, "boom")
        stop.set()
        t.join(5)
        self.assertEqual(violations, [], "failed status and pause must be atomic")
        self.assertIsNone(c.claim(), "paused after failure")

    def test_timeout_marks_and_pauses(self):
        self.add_job(task="slow")

        def slow(argv, kw):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 600)

        self.c.run(execute=True, timeout=5.0, runner=FakeRunner(slow))
        job = self.c.get(1)
        self.assertEqual(job.status, "timed_out")
        self.assertIn("timed out", job.output)
        self.assertTrue(self.c.paused_reason())

    # -- adapter availability ---------------------------------------------------

    def test_claude_unavailable_until_installed(self):
        with self.assertRaises(C.ControllerError) as ctx:
            self.c.add("x", "builder", "claude", self.wt)
            self.assertIn("not authenticated", str(ctx.exception))

    def test_live_uses_list_argv_no_shell(self):
        self.add_job(task="x")
        runner = FakeRunner()
        self.c.run(execute=True, runner=runner)
        self.assertTrue(runner.calls)
        for argv, kw in runner.calls:
            self.assertIsInstance(argv, list, "no shell interpolation")
            self.assertFalse(kw.get("shell"))
            self.assertEqual(kw["cwd"], self.wt)


if __name__ == "__main__":
    unittest.main()

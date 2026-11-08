"""Local agent-workflow controller (Python standard library only).

Supervised by Jacob. Owns a persistent queue of AI worker jobs (SQLite),
claims jobs atomically under a hard managed concurrency cap, dispatches
them to worker CLIs as exact argv lists (no shell, no interpolation),
and records results.

Limits, and what they do NOT claim:
- MAX_MANAGED_JOBS = 2 (initial), HARD_CEILING = 4. Enforced for jobs
  *this controller* dispatches only; the ceiling cannot be raised above
  4 by constructor overrides. They do not count, limit, or measure any
  global provider or request limit (ISU sessions, Codex/Claude
  subscriptions, the deployed site's per-minute cap).
- Dry-run is the default and is strictly read-only: it previews the
  pending jobs and their exact argv WITHOUT changing queue state.
- **All live dispatch is currently disabled** (owner directive
  2026-11-08, pending end-to-end validation). Every adapter has
  live_enabled=False; a live run pauses the controller with the reason
  recorded and returns the job to the queue.
- Pause on failure or timeout; no automatic retries; Jacob resumes.
- State (SQLite DB) and worker output files live OUTSIDE the repository
  (default: %LOCALAPPDATA%\\sec-10k-agent-workflow).
- Never pushes, merges, deploys, installs, stores credentials, or
  spawns subagents.

Lifecycle: Windows workers use kill-on-close Job Objects before execution.
Unsupported platforms refuse launch. Explicit recover interrupts only jobs whose
recorded owner is provably dead, and pauses without retrying.

Usage (from the repo root):
  python tools\\agent_workflow\\controller.py add --task "..." --kind builder --provider codex --worktree ..\\wt
  python tools\\agent_workflow\\controller.py list
  python tools\\agent_workflow\\controller.py run            (dry-run preview; queue state unchanged)
  python tools\\agent_workflow\\controller.py run --execute  (currently pauses: live dispatch disabled)
  python tools\\agent_workflow\\controller.py resume
"""
from __future__ import annotations

import argparse
import processes
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# State and outputs live OUTSIDE the tracked source tree.
DEFAULT_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "sec-10k-agent-workflow"
DEFAULT_DB = DEFAULT_STATE_DIR / "state.db"
DEFAULT_INSTRUCTIONS = REPO_ROOT / "AGENTS.md"

MAX_MANAGED_JOBS = 2   # initial: automation slots
HARD_CEILING = 4       # absolute managed ceiling (not raiseable via overrides)


class ControllerError(Exception):
    pass


OPENCODE_EXE = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "ai.opencode.desktop",
    "resources", "opencode-cli.exe")


@dataclass
class Job:
    id: int
    task: str
    kind: str        # builder | reviewer
    provider: str    # codex | opencode | claude
    worktree: str
    status: str
    exit_code: Optional[int] = None
    output: Optional[str] = None


class Adapter:
    provider = ""
    available = True           # can jobs be enqueued at all
    unavailable_reason = ""
    live_enabled = False       # ALL live dispatch stays disabled until
    live_disabled_reason = ""  # end-to-end validation (owner directive)

    def build_argv(self, job: Job, instructions: Path, out_dir: Path) -> List[str]:
        raise NotImplementedError


def _prompt(job: Job, instructions: Path) -> str:
    # Worktrees are based on origin/main and do NOT contain the unmerged
    # AGENTS.md / AGENT_WORKFLOW.md, so reviewed instructions are supplied
    # explicitly in every prompt.
    return ("FIRST read the reviewed rules in %s (AGENTS.md) and follow them; "
            "this worktree is based on origin/main and does not contain them. "
            "Task: %s" % (instructions, job.task))


class CodexAdapter(Adapter):
    """codex-cli 0.167.0 (verified 2026-11-08). Sandbox flags are
    prepared in the argv (workspace-write builders, read-only reviews),
    but live dispatch stays disabled pending end-to-end validation.

    Windows wrappers are resolved to the installed native binary so
    task text never passes through a command shell.
    """
    provider = "codex"
    live_disabled_reason = (
        "pending end-to-end validation (owner directive 2026-11-08); "
        "sandbox flags prepared in preview")

    def __init__(self, executable: Optional[str] = None):
        self._executable = executable

    def _exe(self) -> str:
        exe = self._executable
        if exe is None:
            exe = shutil.which("codex")
            if exe is None:
                raise ControllerError("codex executable not found on PATH")
            self._executable = exe
        if exe.lower().endswith((".cmd", ".bat")):
            package = Path(exe).parent / "node_modules" / "@openai" / "codex"
            candidates = list(package.glob(
                "node_modules/@openai/codex-*/vendor/*/bin/codex.exe"))
            if len(candidates) != 1:
                raise ControllerError("cannot uniquely resolve native Codex binary")
            exe = str(candidates[0].resolve())
        if exe.lower().endswith(".ps1"):
            raise ControllerError(
                "codex resolved to a PowerShell shim (%s); a .ps1 shim "
                "cannot be launched with shell=False" % exe)
        return exe

    def build_argv(self, job, instructions, out_dir):
        sandbox = "workspace-write" if job.kind == "builder" else "read-only"
        argv = [self._exe(), "exec", "-C", job.worktree, "-s", sandbox]
        if job.kind == "builder":
            argv += ["--json",
                     "-o", str(Path(out_dir) / ("result-%d.txt" % job.id))]
        argv.append(_prompt(job, instructions))
        return argv


class OpenCodeAdapter(Adapter):
    """opencode v2.2.5 (verified 2026-11-08). No verified sandbox mode:
    the help shows no read-only/workspace-write flag, and --auto
    auto-approves permissions, which is not read-only enforcement.
    Live dispatch disabled (as with all adapters) pending end-to-end
    validation; dry-run only."""
    provider = "opencode"
    live_disabled_reason = (
        "no verified sandbox mode (v2.2.5 help has no read-only/"
        "workspace-write flag; --auto is not read-only enforcement) and "
        "live dispatch is disabled pending end-to-end validation")

    def build_argv(self, job, instructions, out_dir):
        return [OPENCODE_EXE, "run", "--auto", "-s", "job-%d" % job.id,
                "-m", "ilstu/ilstu-coder", "--format", "json",
                _prompt(job, instructions)]


class ClaudeAdapter(Adapter):
    provider = "claude"
    available = False
    unavailable_reason = (
        "Claude Code CLI 2.1.319 is installed but not authenticated "
        "(verified 2026-11-08); adapter stays unavailable until sign-in")

    def build_argv(self, job, instructions, out_dir):
        raise ControllerError(self.unavailable_reason)


ADAPTERS: Dict[str, Adapter] = {
    a.provider: a for a in (CodexAdapter(), OpenCodeAdapter(), ClaudeAdapter())
}


class Controller:
    def __init__(self, db_path: Path = DEFAULT_DB,
                 max_jobs: int = MAX_MANAGED_JOBS,
                 ceiling: int = HARD_CEILING,
                 adapters: Optional[Dict[str, Adapter]] = None):
        if ceiling > HARD_CEILING:
            raise ControllerError(
                "ceiling %d exceeds the hard ceiling of %d; not raiseable "
                "by override" % (ceiling, HARD_CEILING))
        if not (1 <= max_jobs <= ceiling):
            raise ControllerError("invalid limits: need 1 <= max_jobs <= ceiling")
        self.db_path = Path(db_path)
        self.state_dir = self.db_path.parent
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.max_jobs = max_jobs
        self.ceiling = ceiling
        self.adapters = dict(ADAPTERS if adapters is None else adapters)
        self.owner = processes.identity()
        self._init_db()

    @contextmanager
    def _db(self):
        """Connection scoped to one operation; always closed on exit.

        (On Windows the DB file stays locked while any connection is
        open, so unclosed connections break cleanup and concurrent use.)
        """
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                kind TEXT NOT NULL,
                provider TEXT NOT NULL,
                worktree TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at REAL,
                finished_at REAL,
                exit_code INTEGER,
                output TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS controller_state (
                key TEXT PRIMARY KEY, value TEXT)""")
            columns = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
            for name, kind in (("owner_host", "TEXT"), ("owner_pid", "INTEGER"),
                               ("owner_birth", "TEXT")):
                if name not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN %s %s" % (name, kind))

    def recover(self) -> List[int]:
        """Explicit recovery; unknown legacy owners require manual investigation."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT id, owner_host, owner_pid, owner_birth "
                              "FROM jobs WHERE status='running'").fetchall()
            for jid, host, pid, birth in rows:
                state = processes.owner_state(host, pid, birth)
                if state != "dead":
                    raise ControllerError("recovery refused: job %d owner %s" % (jid, state))
            for jid, *_ in rows:
                db.execute("UPDATE jobs SET status='interrupted', finished_at=?, "
                           "output='owner abandoned; explicit recovery; no retry' WHERE id=?",
                           (time.time(), jid))
            if rows:
                db.execute("INSERT OR REPLACE INTO controller_state VALUES ('paused', '1')")
                db.execute("INSERT OR REPLACE INTO controller_state VALUES "
                           "('pause_reason', 'interrupted jobs recovered; investigate before resume')")
            return [r[0] for r in rows]

    # ---- queue ----

    def add(self, task: str, kind: str, provider: str, worktree: str) -> int:
        if kind not in ("builder", "reviewer"):
            raise ControllerError("kind must be builder|reviewer")
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise ControllerError("unknown provider: %s" % provider)
        if not adapter.available:
            raise ControllerError("adapter unavailable: %s" % adapter.unavailable_reason)
        wt = str(Path(worktree).resolve())
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO jobs (task, kind, provider, worktree, status) "
                "VALUES (?, ?, ?, ?, 'pending')", (task, kind, provider, wt))
            return int(cur.lastrowid)

    def claim(self) -> Optional[int]:
        """Atomically claim the oldest claimable pending job.

        One BEGIN IMMEDIATE transaction: pause check, managed-cap check,
        worktree-exclusivity check (a job is never claimed while another
        job is running in the same resolved worktree), then the status
        change. Concurrent claimants can never double-claim or exceed
        the cap.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            paused = db.execute(
                "SELECT value FROM controller_state WHERE key='paused'").fetchone()
            if paused and paused[0] == "1":
                db.execute("COMMIT")
                return None
            running = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
            if running >= self.max_jobs or running >= self.ceiling:
                db.execute("COMMIT")
                return None
            rows = db.execute(
                "SELECT id, worktree FROM jobs WHERE status='pending' ORDER BY id"
            ).fetchall()
            chosen = None
            for jid, wt in rows:
                clash = db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status='running' AND worktree=?",
                    (wt,)).fetchone()[0]
                if clash == 0:
                    chosen = jid
                    break
            if chosen is None:
                db.execute("COMMIT")
                return None
            db.execute(
                "UPDATE jobs SET status='running', started_at=?, "
                "owner_host=?, owner_pid=?, owner_birth=? "
                "WHERE id=? AND status='pending'", (time.time(), *self.owner, chosen))
            db.execute("COMMIT")
            return int(chosen)

    def settle(self, job_id: int, status: str,
               exit_code: Optional[int], output: str) -> None:
        """Finish a job; failure status and the pause land in ONE
        transaction so a claim can never observe 'job finished' without
        the pause already being visible (no claim race)."""
        with self._db() as db:
            db.execute(
                "UPDATE jobs SET status=?, finished_at=?, exit_code=?, output=? "
                "WHERE id=?", (status, time.time(), exit_code, output, job_id))
            if status in ("failed", "timed_out", "interrupted"):
                db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                           "VALUES ('paused', '1')")
                db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                           "VALUES ('pause_reason', ?)",
                           ("job %d %s" % (job_id, status),))

    def refuse(self, job_id: int, reason: str) -> None:
        """Return a claimed job to the queue and pause the controller,
        in one transaction, when its adapter has no live dispatch."""
        with self._db() as db:
            db.execute(
                "UPDATE jobs SET status='pending', started_at=NULL WHERE id=?",
                (job_id,))
            db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                       "VALUES ('paused', '1')")
            db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                       "VALUES ('pause_reason', ?)",
                       ("live dispatch disabled: %s (job %d returned to queue)"
                        % (reason, job_id),))

    def get(self, job_id: int) -> Job:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ControllerError("no such job: %d" % job_id)
        return self._job(row)

    def all_jobs(self) -> List[Job]:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        return [self._job(r) for r in rows]

    @staticmethod
    def _job(row) -> Job:
        return Job(id=row["id"], task=row["task"], kind=row["kind"],
                   provider=row["provider"], worktree=row["worktree"],
                   status=row["status"], exit_code=row["exit_code"],
                   output=row["output"])

    def counts(self) -> dict:
        with self._db() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        return dict(rows)

    # ---- pause / resume ----

    def pause(self, reason: str) -> None:
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                       "VALUES ('paused', '1')")
            db.execute("INSERT OR IGNORE INTO controller_state (key, value) "
                       "VALUES ('pause_reason', ?)", (reason,))

    def resume(self) -> None:
        with self._db() as db:
            db.execute(
                "DELETE FROM controller_state WHERE key IN ('paused', 'pause_reason')")

    def paused_reason(self) -> str:
        with self._db() as db:
            p = db.execute(
                "SELECT value FROM controller_state WHERE key='paused'").fetchone()
            if not p or p[0] != "1":
                return ""
            r = db.execute(
                "SELECT value FROM controller_state WHERE key='pause_reason'").fetchone()
            return r[0] if r else ""

    # ---- dispatch ----

    def preview(self, instructions: Path = DEFAULT_INSTRUCTIONS
                ) -> List[Tuple[int, List[str]]]:
        """Read-only dry-run: pending jobs and the exact argv that WOULD
        run. Makes no changes to queue state."""
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, task, kind, provider, worktree "
                "FROM jobs WHERE status='pending' ORDER BY id").fetchall()
        out: List[Tuple[int, List[str]]] = []
        for row in rows:
            job = Job(id=row["id"], task=row["task"], kind=row["kind"],
                      provider=row["provider"], worktree=row["worktree"],
                      status="pending")
            out.append((job.id, self.adapters[job.provider].build_argv(
                job, instructions, self.state_dir)))
        return out

    def run(self, execute: bool = False, timeout: float = 600.0,
            instructions: Path = DEFAULT_INSTRUCTIONS,
            runner: Callable = processes.run) -> List[int]:
        """One dispatch pass.

        Dry-run (default): strictly read-only preview of pending jobs;
        returns their ids; queue state is unchanged.
        Live (execute=True): claims under the managed cap and dispatches
        adapter argv lists through `runner` (no shell). Jobs whose
        adapter has no live dispatch are returned to the queue and the
        controller pauses. Returns the ids processed (to a terminal
        state) this pass.
        """
        if not execute:
            return [job_id for job_id, _ in self.preview(instructions)]
        futures = []
        cancel = threading.Event()
        with ThreadPoolExecutor(max_workers=self.max_jobs) as pool:
            try:
                while True:
                    job_id = self.claim()
                    if job_id is None:
                        break
                    job = self.get(job_id)
                    adapter = self.adapters[job.provider]
                    if not adapter.live_enabled:
                        self.refuse(job_id, adapter.live_disabled_reason)
                        break  # controller is paused; end this pass
                    futures.append(pool.submit(self._run_live, job, timeout,
                                               instructions, runner, cancel))

                return [fut.result() for fut in as_completed(futures)]
            except BaseException:
                cancel.set()
                raise

    def _run_live(self, job: Job, timeout: float, instructions: Path,
                  runner: Callable, cancel=None) -> int:
        adapter = self.adapters[job.provider]
        status, code, output = "done", 0, ""
        try:
            argv = adapter.build_argv(job, instructions, self.state_dir)
            kwargs = dict(cwd=job.worktree, timeout=timeout,
                          capture_output=True, text=True, shell=False)
            if runner is processes.run:
                kwargs['cancel_event'] = cancel
            proc = runner(argv, **kwargs)
            code = int(proc.returncode)
            output = ((proc.stdout or "")[-4000:]
                      + "\n[stderr]\n" + (proc.stderr or "")[-2000:])
            if code != 0:
                status = "failed"
        except (KeyboardInterrupt, SystemExit):
            self.settle(job.id, "interrupted", None, "controller interrupted; no retry")
            raise
        except subprocess.TimeoutExpired:
            status, code = "timed_out", None
            output = "timed out after %.0f seconds" % timeout
        except InterruptedError:
            status, code, output = "interrupted", None, "controller interrupted; no retry"
        except Exception as exc:
            status, code = "failed", None
            output = "launch error: %r" % exc
        self.settle(job.id, status, code, output)
        return job.id


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Local agent-workflow controller (stdlib only, supervised by Jacob)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="enqueue a job")
    p.add_argument("--task", required=True)
    p.add_argument("--kind", choices=("builder", "reviewer"), required=True)
    p.add_argument("--provider", choices=tuple(ADAPTERS), required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--db", default=str(DEFAULT_DB))

    p = sub.add_parser("run",
                       help="one pass: dry-run preview (default) or live dispatch")
    p.add_argument("--execute", action="store_true",
                   help="attempt live dispatch (all adapters currently disabled)")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="per-job timeout in seconds (default 600)")
    p.add_argument("--db", default=str(DEFAULT_DB))

    for name, help_ in (("recover", "recover provably abandoned jobs and pause"),
                        ("list", "show jobs and pause state"),
                        ("resume", "clear a pause (Jacob only)")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--db", default=str(DEFAULT_DB))

    args = ap.parse_args(argv)
    c = Controller(Path(args.db))
    try:
        if args.cmd == "add":
            jid = c.add(args.task, args.kind, args.provider, args.worktree)
            print("added job %d (%s %s)" % (jid, args.provider, args.kind))
        elif args.cmd == "run":
            if not args.execute:
                print("controller: DRY-RUN preview (queue state unchanged), "
                      "max %d managed jobs (ceiling %d)" % (c.max_jobs, c.ceiling))
                for jid, argv in c.preview():
                    print("job %d: PENDING (nothing launched): %s"
                          % (jid, " ".join(argv)[:120]))
            else:
                print("controller: LIVE pass requested, max %d managed jobs "
                      "(ceiling %d)" % (c.max_jobs, c.ceiling))
                for jid in c.run(execute=True, timeout=args.timeout):
                    job = c.get(jid)
                    first = (job.output or "").splitlines()[0]
                    print("job %d: %s  %s" % (jid, job.status, first[:120]))
        elif args.cmd == "list":
            reason = c.paused_reason()
            if reason:
                print("PAUSED: %s  (resume: controller.py resume)" % reason)
            for job in c.all_jobs():
                print("%3d  %-9s  %-8s  %-8s  rc=%-4s %s"
                      % (job.id, job.status, job.provider, job.kind,
                         job.exit_code, (job.output or "")[:80]))
        elif args.cmd == "recover":
            print("recovered interrupted jobs: %s" % c.recover())
        elif args.cmd == "resume":
            c.resume()
            print("resumed")
    except ControllerError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

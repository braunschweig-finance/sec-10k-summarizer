# Agent workflow controller quickstart

Local, Jacob-supervised SQLite job queue; Python standard library only.
Run the examples from the repository root with an existing Python installation.
Read `AGENTS.md` first. Use a separate existing branch/worktree for each task;
the controller records the worktree path but does not create or validate it.

## Queue and preview

```powershell
python tools/agent_workflow/controller.py add --task "Review documentation for accuracy" --kind reviewer --provider codex --worktree "../sec-10k-summarizer-doc-review"
python tools/agent_workflow/controller.py list
python tools/agent_workflow/controller.py run
```

`add` persists a pending job. `list` shows jobs and any pause reason.
`run` defaults to dry-run: **pending jobs remain unchanged**, nothing launches,
and no job is claimed or completed. Previewing is not a successful execution.
The CLI prints only the first 120 characters of each joined argv preview.
Codex preview requires a resolvable installed Codex executable; it does not run it.

Required `add` flags: `--task`, `--kind` (`builder` or `reviewer`),
`--provider` (`codex`, `opencode`, or `claude`), and `--worktree`.
Claude is accepted by the parser but rejected by the unavailable adapter.

State defaults to `%LOCALAPPDATA%/sec-10k-agent-workflow/state.db`, outside
the repository (home directory fallback if `LOCALAPPDATA` is unset).
Worker result files also use the state directory.
Every subcommand accepts `--db PATH`; put it after the subcommand and use
the same external database path for add, list, run, recover, and resume.

## Limits and current live status

- Initial cap: **two managed jobs**, with a **hard ceiling of four**.
  These are controller-managed job limits, not global request enforcement.
  They do not count other controllers using other databases, interactive CLI
  sessions, provider requests, or the deployed site's per-minute limiter.
  There is no CLI flag to raise these limits.
- Claims are atomic within the shared database and exclude worktrees that
  already have a running job in that database.
- **All live adapters are disabled** pending end-to-end validation.
  `run --execute` attempts a live pass; when it claims a job with a disabled
  adapter, it returns that job to pending and pauses with a recorded reason.
  It does not launch the worker.
- **Claude is temporarily paused by Jacob**; do not dispatch it, use it as
  fallback, or resume its use without his explicit re-enablement.
  Its adapter is also unavailable. Use Codex/ISU-backed OpenCode for trials.
- OpenCode has no verified sandbox mode; `--auto` is not read-only enforcement.
  Prepared Codex sandbox flags have not established end-to-end validation.

## Pauses and recovery limitations

Failures and timeouts pause dispatch; there are no automatic retries.
Jacob alone clears a pause with:

```powershell
python tools/agent_workflow/controller.py resume
```

`resume` only clears the pause; it does not retry or repair jobs, enable live
adapters, or re-enable Claude. `run --timeout SECONDS` sets the per-job timeout
(default 600 seconds), relevant only to live execution once enabled.
The Windows runner contains workers and descendants in kill-on-close Job Objects
before execution. Unsupported platforms refuse real dispatch. Controller death
before assignment can leave an inert suspended process; this remains documented.
After interruption, `recover` verifies the recorded owner is provably dead,
marks abandoned jobs `interrupted`, and pauses. Living or uncertain owners cause
refusal. It never kills by stored PID or automatically retries/requeues jobs.
Investigate before `resume`; interrupted jobs remain terminal.

## Help and offline tests

```powershell
python tools/agent_workflow/controller.py --help
python tools/agent_workflow/controller.py add --help
python tools/agent_workflow/controller.py list --help
python tools/agent_workflow/controller.py run --help
python tools/agent_workflow/controller.py recover --help
python tools/agent_workflow/controller.py resume --help
python -m unittest discover -s tools/agent_workflow/tests -p "test_controller.py" -v
```

Tests use fake adapters and local Python fixtures, with no real AI or network calls.
The controller does not install, push, merge, deploy, store credentials,
or spawn subagents. Repository policy still prohibits subagents.

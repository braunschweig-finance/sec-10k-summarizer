# AGENT_WORKFLOW.md — local multi-agent development workflow

Companion to `AGENTS.md` (the binding rules). This file describes **how** the local setup actually runs: a local controller program, supervised by Jacob, directing up to four AI workers — OpenCode on ISU Adaptive Edge, Codex on a personal ChatGPT login, and (once installed) Claude Code on a personal subscription — in separate worktrees, coordinated through a persistent task queue, with all merging done by hand.

Everything in this file that says "verified 2026-11-08" was checked on the owner's laptop that day (versions, help output, login status, reachability). Nothing here is technical enforcement: the worker cap, the queue discipline, and the merge rules are policy until code or GitHub settings make them real (see the enforcement table in `AGENTS.md`).

## Roles

- **Controller (local program, supervised by Jacob).** A small standard-library Python program, `tools/agent_workflow/controller.py`, owns the persistent task queue (SQLite), claims jobs atomically under a hard managed cap (two concurrent managed jobs, ceiling four), dispatches them to worker CLIs as exact command lines, and records results. It is dry-run by default, pauses on failure, never retries, stores no credentials, and never pushes or merges. Jacob supervises: he decides what enters the queue, investigates and clears pauses, reads the reviewer verdicts, and merges by hand.
- **Builder.** One AI agent per task, working in its own worktree. Implements, adds/updates tests, runs the build and test commands from `AGENTS.md`, commits to its branch, and reports what changed and what was checked. A builder never reviews or merges its own work.
- **Reviewer.** A different agent, in a fresh session, ideally on a different provider/model than the builder. Reads the branch diff plus `AGENTS.md`, independently re-runs the relevant checks, verifies every number traces to a filing, and posts a written verdict (approve / request changes) with evidence. The reviewer reports problems; it does not fix code.
- **AI review is evidence, not an approval.** The verdict informs Jacob's manual merge decision. It never counts as a GitHub required approval, and the PR author cannot approve their own PR — which matters here because agents commit under the owner's account, so the owner is usually the author.

## Worker limits

- **Managed-worker cap (enforced by the local controller):** at most **two concurrent managed jobs**, with an absolute ceiling of **four**. Managed jobs are the unattended automation slots (the controller's initial two); the other two slots stay for interactive sessions where Jacob drives an agent directly.
- **Not global enforcement.** The managed cap counts only jobs the controller dispatches. It does not count, limit, or measure any other AI request — not ISU's reported session cap, not Codex/Claude subscription limits, and not the deployed site's per-minute cap. The four-worker planning number across all AI activity remains conservative owner policy.
- **Provider budgets are separate and each applies only to its own requests:**
  - **ISU Adaptive Edge** (via OpenCode, provider `ilstu`): university-paid. ISU policy: school work only, public data only — never route keys or personal data through it. ISU's reported four-concurrent-session cap (2026-10-26 interview; exact scope unconfirmed) binds ISU requests only.
  - **Codex** (personal ChatGPT login): consumes Jacob's own subscription.
  - **Claude Code** (personal subscription): consumes Jacob's own subscription.
  - One worker on any one provider does not free up a slot on another provider, and ISU limits do not transfer to personal Codex/Claude usage — the four-worker cap is the project's own guardrail on top of each provider's limits.
- **No paid calls without an explicit go-ahead.** Interactive use of a personal Codex or Claude Code session spends the owner's subscription; dispatch such a worker only when the task is worth it.
- **No subagents** (per `AGENTS.md`; bounded subagent concurrency comes later, explicitly, after a shared limiter exists).

## Task queue (persistent, local)

- The persistent queue is the controller's **SQLite database** (`tools/agent_workflow/state.db`, local to the machine, never committed). It stays out of the public repo so internal state, session IDs, and verdicts are never published.
- **Only the controller program writes the queue.** Workers and humans never edit it by hand; Jacob supervises through the CLI (`add`, `list`, `run`, `resume`).
- Each job records: task, kind (builder/reviewer), provider, worktree, status, exit code, and the output tail.
- Job statuses: `pending` → `running` → `done` | `failed` | `timed_out` | `interrupted`. Any failure or timeout **pauses** the controller (reason stored); Jacob resumes it explicitly. No automatic retries.
- Claiming is **atomic** (SQLite `BEGIN IMMEDIATE` transaction): the pause check, the managed-cap check, the worktree-exclusivity check (no two running jobs may share a resolved worktree), and the status change all happen in the same transaction, so concurrent claims can never double-claim or exceed the cap.
- **All live dispatch is currently disabled** (owner directive 2026-11-08, pending end-to-end validation). Any live run pauses the controller with the reason recorded and returns the job to the queue; dry-run previews never change queue state. (OpenCode additionally lacks a verified sandbox mode; the Claude Code CLI is uninstalled.)
- State (SQLite DB) and worker output files live outside the repo, in `%LOCALAPPDATA%\sec-10k-agent-workflow`.

## Worktrees

- One task = one branch = one worktree. Never share a working directory between tasks; never let two workers touch one branch.
- Create (from any checkout, after `git fetch origin`):
  `git worktree add ..\sec-10k-summarizer-<task> -b <branch> origin/main`
- A new worktree based on `origin/main` does **not** contain the unmerged `AGENTS.md` / `AGENT_WORKFLOW.md`. Dispatch prompts must supply the reviewed instructions explicitly: the controller points every worker at the reviewed `AGENTS.md` in the main checkout and carries the task text in the prompt.
- Remove with `git worktree remove ..\sec-10k-summarizer-<task>` after the PR is merged (and delete the local branch).
- Codex has a built-in `--worktree` flag that runs a session in a new managed worktree. It works, but controller-created worktrees are preferred so the queue's bookkeeping (paths, branches) stays under the controller.

## Unattended invocation (from actual CLI help, verified 2026-11-08)

### OpenCode on ISU (installed, authenticated)

- Binary (not on PATH — use the full path): `C:\Users\Jacob\AppData\Local\Programs\ai.opencode.desktop\resources\opencode-cli.exe`
- Version `v2.2.5`; `auth list` shows the `ilstu` provider stored.
- Unattended form: `opencode run [flags] [<message...>]` — run with the task worktree as the current directory:
  - `--session, -s <id>` — continue a session, or create it with that ID (use a stable ID per task so the controller can resume)
  - `--continue, -c` / `--fork` — continue last session / fork before continuing
  - `--model, -m provider/model#variant` — e.g. `ilstu/ilstu-coder`
  - `--format json` — machine-readable output
  - `--auto` — auto-approve permissions that are not explicitly denied. **Not read-only enforcement:** the v2.2.5 help shows no read-only or workspace-write sandbox flag, so the controller leaves OpenCode **live dispatch disabled** (dry-run only) until a sandboxed mode exists and is verified.

  Example: `& "$env:LOCALAPPDATA\Programs\ai.opencode.desktop\resources\opencode-cli.exe" run --auto -s task-001 -m ilstu/ilstu-coder --format json "Read AGENTS.md, then implement: <task>"`

### Codex on personal ChatGPT (installed, authenticated)

- `codex` on PATH (npm global `@openai`, shim `C:\Users\Jacob\AppData\Roaming\npm\codex.ps1`); `codex-cli 0.167.0`; `codex login status` → "Logged in using ChatGPT".
- Unattended form: `codex exec [OPTIONS] [PROMPT]` — prompt as an argument, or on stdin (use `-`); subcommands `resume` (by ID or `--last`), `fork`, `review`.
- Flags relevant to dispatching:
  - `-C, --cd <DIR>` — run with the task worktree as the working root
  - `-s, --sandbox read-only|workspace-write|danger-full-access` — `workspace-write` for builders, `read-only` for reviewers; never `danger-full-access`
  - Do not combine `--approve-for-me` with `--sandbox`: CLI 0.167.0 rejects that combination. Initial trials use explicit sandbox settings without this flag.
  - `-m, --model <MODEL>` — pick a model; `-c key=value` — override any `config.toml` value
  - `--json` — print events as JSONL for the controller to parse
  - `-o, --output-last-message <FILE>` — capture the agent's final message to a file
  - `--ephemeral` — no session files on disk (not needed when the queue records the session ID)
- Example (builder): `codex exec -C ..\sec-10k-summarizer-<task> -s workspace-write --json -o result-001.txt "Read AGENTS.md, then implement: <task>"`
- **Initial reviews use Codex read-only:** `codex exec -C ..\sec-10k-summarizer-<task> -s read-only "<review prompt>"` — reviewers never run with write access. (`codex review` / `codex exec review` give a repo-wide non-interactive pass.)

### Claude Code on personal subscription (not installed)

- No `claude` on PATH, no npm shim, no `@anthropic-ai` package; only the Claude Desktop app is present. Unattended mode will be documented here, from `claude --help`, once the CLI is installed and logged in (expected: a non-interactive print mode; do not rely on it until verified).

### GitHub CLI (installed, not logged in)

- `gh` 2.103.3 at `C:\Program Files\GitHub CLI\gh.exe`; `gh auth status` → not logged into any host.
- Until `gh auth login` (Jacob's action, requires a browser sign-in), PRs are created from the GitHub web UI after the builder pushes its feature branch. Pushing feature branches is fine; direct pushes to `main` are not.

## Merge flow (manual, no exceptions)

1. Builder finishes, commits to its branch, pushes the branch, and reports (worktree, branch, checks run, files changed).
2. Jacob enqueues a reviewer job and the controller dispatches it (fresh session, read-only — Codex read-only initially; a different provider/model when one is live-enabled) on the same branch.
3. Reviewer posts a written verdict with evidence to the task entry.
4. **Jacob merges by hand** (web UI or `gh`), then removes the worktree and local branch and marks the task `MERGED`.
- GitHub auto-merge stays off on every PR. If a required-approval rule is ever added to branch protection, it must be satisfiable by an eligible separate account or a properly configured bot — never by the PR author.

## Local build and test status (verified 2026-11-08; installs deferred)

| Tool | Version | State |
|---|---|---|
| git | 2.55.0.windows.5 | ready |
| Python | 3.13.2 (+ pip) | matches CI (3.13); no venv created in the clone yet |
| Node / npm | v24.22.1 / 11.19.1 | ready; no `web/node_modules` yet |
| SEC EDGAR | — | reachable from the laptop (HTTP 200, 2026-11-08) |

- `api/requirements.txt` pins 11 packages and **does not include pytest**; CI installs it separately. Local API test env (from the **repo root**): `python -m venv .venv`, then `.venv\Scripts\pip install -r api\requirements.txt pytest`; run tests from `api/` with that interpreter: `..\venv\Scripts\python -m pytest tests -q`.
- What can run **right now** (standard library only, no installs): the workflow controller and its offline tests — `python tools\agent_workflow\tests\test_controller.py` from the repo root (fake workers, launches nothing).
- What can run once those (deferred, owner-approved) installs exist:
  - **Unit tests** — from `api/`, with the root venv: `..\venv\Scripts\python -m pytest tests -q` (offline fixtures; no API keys, no paid calls).
  - **Live SEC checks** — `python tests/live_check.py [TICKERS]`, `live_alerts.py` (public data only).
  - **Web build** — `npm install` then `npm run build` from `web/` (required before any front-end PR; there is no CI gate for `web/`).
  - **Live AI checks** — need an AI provider; use ISU only for school work on public data, and count the call against the worker cap.
- Nothing that needs dependencies can run in the fresh clone yet (no venv, no node_modules). That is intentional — installation is a separate, owner-approved step.

## Safety rails

- **Never expose credentials** (per `AGENTS.md`): no keys, tokens, or session secrets in the queue file, worktrees, commits, or reports. The queue file lives outside the repo precisely so internal state stays private.
- **ISU ToS**: school work only, public data only; never send keys or personal data through the ISU proxy.
- **No paid calls without an explicit go-ahead** (personal Codex/Claude sessions spend the owner's subscriptions; live AI checks spend ISU quota).
- **Workers never merge, never enable auto-merge, never push to `main`, never spawn subagents.**
- The **managed-worker** cap (two jobs, ceiling four) is enforced by the controller for the jobs it dispatches; the four-worker planning number across *all* AI activity (managed + interactive) remains policy-only. Bounded subagent concurrency comes later, by explicit revision of `AGENTS.md`, not by habit.

## Controller lifecycle (Windows fixture tests passed)

- The default runner is Windows-only and uses a non-inheritable, kill-on-close Job Object. Each worker is created suspended, assigned to the job, then resumed. Assignment or setup failure refuses execution and terminates the exact suspended process handle. Descendants inherit containment, with no breakaway enabled. Timeout, cancellation, normal completion, and controller process death close the job handle; no process-name or broad PID kills are used. Ctrl+C cancels active default runners before executor shutdown.
- Unsupported platforms or Windows environments that reject Job Object assignment fail closed. Fake injected runners remain available for offline unit tests; they do not provide OS containment. Abrupt death in the narrow create-suspended/before-assignment interval can leave an inert suspended process; worker code cannot execute before assignment.
- Claims durably record the controller host, PID, and Windows process creation time in the same transaction as `running`. `recover --db <path>` checks every running owner under an exclusive write transaction. A living owner, inaccessible process, foreign host, missing identity, or unsupported identity check refuses the entire recovery pass. PID reuse is checked using creation time. Recovery never kills by stored PID.
- Only provably abandoned jobs become terminal `interrupted`; recovery atomically pauses dispatch. There is no automatic startup recovery, retry, or requeue. Inspect results, then use `resume` explicitly; interrupted jobs remain terminal. Enqueue any replacement only after investigation.
- Existing SQLite databases migrate additively on opening. Old rows remain intact; legacy running rows have unknown ownership and cannot be automatically recovered. Do not infer abandonment from elapsed time or edit the database to guess ownership.
- All production adapters remain live-disabled. These lifecycle changes do not authorize live AI trials.
- Offline checks: `python -m unittest discover -s tools/agent_workflow/tests -p "test_*.py"`. The original fake-runner checks remain; new Windows-only tests launch local Python fixtures for descendant timeout and abrupt controller death, then test explicit recovery. No AI is launched. The supervisor verified all 29 tests on native Windows, including real fixture descendants and controller termination; production AI adapters remain disabled.

## Minimal end-to-end example

```powershell
# 1. Controller: fetch and create the worktree (from any checkout of the repo)
git fetch origin
git worktree add ..\sec-10k-summarizer-fix-x -b fix/x origin/main

# 2. Controller: enqueue and dispatch a builder (dry-run is the default; --execute launches)
python tools\agent_workflow\controller.py add --task "<task>" --kind builder --provider codex --worktree ..\sec-10k-summarizer-fix-x
python tools\agent_workflow\controller.py run --execute

# 3. Builder pushes its branch (feature branch only); Jacob enqueues a reviewer job
# 4. Controller: dispatch the reviewer — Codex read-only, pointing at the reviewed rules
#    (the worktree is from origin/main and lacks the unmerged AGENTS.md)
python tools\agent_workflow\controller.py add --task "Review branch fix/x: re-run checks, verify number traceability, post a verdict with evidence" --kind reviewer --provider codex --worktree ..\sec-10k-summarizer-fix-x
python tools\agent_workflow\controller.py run --execute

# 5. Jacob reads the verdict (controller.py list), merges by hand, then:
git worktree remove ..\sec-10k-summarizer-fix-x
```

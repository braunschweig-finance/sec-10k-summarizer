# AGENTS.md — Rules for AI contributors in this repository

Read this before doing any work here. These are instructions for AI contributors to this repository (OpenCode, Claude Code, Codex, or any other agent). Full project background lives outside the repo at `C:\Users\Jacob\OneDrive\Claude AI\Finance Research CLAUDE.md` (on the owner's laptop) — read it if you have access.

Temporary provider policy: Claude Code usage is paused at Jacob's request because his weekly allowance is nearly exhausted. Do not dispatch Claude, use it as fallback, or resume it without Jacob explicitly re-enabling it. Use Codex and ISU-backed OpenCode only for development trials. This does not change the deployed website's provider settings.

## Project purpose

A better SEC 10-K and corporate governance app. It pulls audited numbers from SEC EDGAR (XBRL), computes ratios and original metrics (Pay Efficiency, Fair Value, company Grade, red flags, insider trades) in deterministic Python, reads DEF 14A proxy statements for governance, and uses AI only for prose — with every AI quote checked word for word against the filing it came from.

**Hard rule: every number the app shows must trace to a filing** (10-K, DEF 14A, 8-K, Form 4) or another reliable source, with the citation kept next to the number. Double-check the math before anything goes into the app.

## Architecture (monorepo, three deployables)

Verified at commit 911bef7 (2026-11-01):

| Path | What it is | Where it runs | Live address |
|---|---|---|---|
| `app.py` + root `requirements.txt` | Original Streamlit app (reference implementation) | Streamlit Cloud | sec-10k-summarizer.streamlit.app |
| `web/` | Next.js 16 + React 19 + Tailwind 4 + Motion front end | Vercel, root directory `web`, env var `NEXT_PUBLIC_API_URL` | sec-10k-summarizer.vercel.app |
| `api/` | FastAPI back end; all deterministic math lives here (`sec_core.py` plus feature modules); AI only through `ai_client.py` | Render free plan, blueprint `render.yaml` | sec-terminal-api.onrender.com |

- `.github/workflows/`: `feature-check.yml` (API PR gate), `ai-readers-check.yml` (AI-reader PR gate), `prebuild.yml` (weekly prebuild, publishes the `prebuilt-data` release), `keep-warm.yml` (keeps the free Render instance awake).
- `docs/LOCAL_AI.md`: how to point the app's AI at a free or local model (`AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`).
- Data: SEC companyfacts XBRL, submissions JSON, DEF 14A primary documents, 8-K exhibits, Form 4 data. `prebuild.yml` publishes precomputed results as the `prebuilt-data` release; `api/prebuilt.py` downloads it.
- As of 2026-11-01 the live app's AI runs on ISU Adaptive Edge (a university-provided service; see the project log). University policy: school work only, public data only — never send keys or personal data through it.

## Build and test commands

Transcribed from the repo's own files (`package.json`, `render.yaml`, workflow YAMLs, `web/README.md`) at 911bef7. CI runs the API ones; nothing has been executed in a fresh local checkout yet (no dependencies installed). Python 3.13.

API — run from `api/`:

```bash
pip install -r requirements.txt
uvicorn main:app --reload              # local server on http://localhost:8000
python -m pytest tests -q              # unit tests (offline fixtures)
python tests/live_check.py [TICKERS]   # live check against SEC EDGAR
python tests/live_alerts.py [TICKERS]  # live red-flag / insider check
python tests/live_check_ai_readers.py  # live AI-reader check (needs an AI key; CI uses the GEMINI_API_KEY secret)
```

Web — run from `web/`:

```bash
npm install
npm run dev                            # http://localhost:3000
npm run build                          # production build — run before opening any front-end PR (no CI gate for web/)
npm run start
npm run preview:build                  # single-file static preview -> preview/dist/index.html
```

Optional local API pointer: `web/.env.local` may set `NEXT_PUBLIC_API_URL` (e.g. `http://localhost:8000`); blank or missing means the site runs on the built-in Caterpillar FY2025 sample. If `.env.local` already exists, edit it in place — do not recreate or overwrite it.

Streamlit legacy app — run from the repo root:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Financial accuracy and source traceability

- Never display a number without its source: XBRL concept + filing accession for 10-K figures, the source sentence for proxy text. The web UI shows tags on hover; the Excel/PDF exports list every tag — keep both working.
- All math is deterministic Python in `api/` (mirrored by `app.py`). AI never computes a number. When a formula changes: add a unit test with a hand-checkable fixture, and recompute at least one real company from its filing by hand before the PR is opened.
- Every AI-produced quote must be verified verbatim against the filing text it came from. Answers whose quote is not in the filing do not count (the governance policy reader already implements this — keep it that way).
- When a data source fails, show the honest "SEC data unavailable" message. Never fabricate, estimate, or silently substitute a value.

## Two-agent roles: builder and independent reviewer

**Automatic merging is disabled. The owner (Jacob) merges every pull request by hand.**

1. **Builder** — one agent per task, working on its own branch in its own worktree (below). Implements the change, adds or updates tests, runs the build/test commands above, and opens a pull request describing what changed and what was checked. A builder never merges its own PR and never reviews its own work.
2. **Reviewer** — a different agent (a fresh session, ideally a different model) that did not write the change. It reads the PR diff plus this file, independently re-runs the relevant checks, verifies every new or changed number traces to a filing, and posts a written verdict (approve / request changes) with the evidence. The reviewer reports problems; it does not fix the code.
3. **Jacob** reads the verdict and merges manually. If the reviewer requests changes, the builder revises on the same branch and the reviewer re-checks.

**AI review is evidence, not an approval.** The reviewer's verdict is written evidence for Jacob's judgment. It does not automatically satisfy GitHub's required-approval rules, and GitHub's own rules apply on top: **the author of a PR cannot approve their own PR**. A required approval must come from an eligible separate account — another human collaborator, or a bot/GitHub App that is appropriately configured to post legitimate review approvals. In this repo, PRs are usually authored under the owner's account (the agents commit with it), so the owner cannot serve as the required reviewer for his own PRs. Until an eligible separate account or configured bot exists, keep branch protection free of a required-approval rule and let Jacob merge manually.

## Concurrent work: separate worktrees

- One task = one branch = one worktree. Never share a working directory between agents or tasks, and never let two agents edit the same branch.
- Create: `git worktree add ..\sec-10k-summarizer-<task> -b <branch>` — remove with `git worktree remove` once the PR is merged.
- Refresh against `origin/main` (fetch + rebase) right before opening the PR.

## Git and merge rules

- **No direct pushes to `main`.** All work goes through a feature branch and a pull request.
- **GitHub auto-merge stays off.** Do not enable "auto-merge" on any pull request.
- Merges happen only by Jacob, by hand, after the reviewer's verdict.
- Commit messages: short, descriptive, one line.

## Changes that need the owner's explicit approval

Do not merge (and flag in the PR description) without Jacob's sign-off:

- Any change to a **financial method or formula** — ratios, Pay Efficiency, fair value, grade weights, red-flag rules, sector mappings.
- Anything touching **credentials, keys, or secrets** — env-var handling, `ai_client.py` authentication, GitHub secrets, Render environment.
- Any **deployment change** — `render.yaml`, Vercel settings, workflow triggers that publish data (`prebuild.yml`), new services or schedules.

## AI request limits (two different kinds — do not conflate them)

**Simultaneous requests (concurrency):**
- Maximum **four simultaneous AI requests** across this project. Initially **two of the four are automation slots** (CI jobs, scheduled prebuilds, batch work); the other two stay reserved for interactive work.
- The four-request figure is **reported by the provider, not measured here**. At the 2026-10-26 ISU interview, ISU Adaptive Edge was described as computing four sessions at once with the rest queued. The exact scope of that constraint (per key, per machine, or per service) and whether a hard global limiter exists are **unconfirmed**. Until ISU confirms it, treat four as a planning number, not a guarantee.
- Nothing in this repository enforces the simultaneous-request cap. In particular, the live app's per-minute rate limiter (below) does **not** count OpenCode sessions or local agent concurrency.

**Requests per minute (throughput):**
- The deployed website caps new AI calls at `AI_CALLS_PER_MINUTE` (default 8 per minute, `api/ai_routes.py`); `api/ai_client.py` reports server rate limits (HTTP 429) as "try again" busy errors instead of looping retries. Keep both behaviors.
- That limiter governs **public calls to the deployed site only**. It neither enforces nor measures how many local agents or OpenCode sessions may run concurrently.

**Subagents: initially prohibited.**
- Agents in this repository must **not spawn subagents at all**. Bounded subagent concurrency will be enabled later, explicitly, in a revision of this file, after a shared limiter for AI requests is implemented. Until then: zero subagents.

## Credentials

- **Never expose credentials.** No API keys, tokens, passwords, or personal account data may appear in code, commits, pull request descriptions, issues, chat logs, screenshots, or exports.
- Keys live only in: the Render dashboard (environment variables), GitHub repository secrets, and the owner's local OpenCode config (`C:\Users\Jacob\.config\opencode`, outside this repo).
- This repository is **public**. Assume everything committed here is visible to the world; only public data (SEC filings, code, results) ever goes in.
- If a key is pasted into a conversation or file by mistake, treat it as compromised: tell Jacob at once and do not repeat the key in the report.

## Enforcement status (read before relying on any rule above)

Instructions in this file do not enforce themselves. Status as of 2026-11-08:

| Rule | Enforced technically today? |
|---|---|
| No direct pushes to `main` | **No.** Branch protection on `main` is off (verified 2026-11-08 via the GitHub API); anyone with push access can push straight to `main`. |
| Auto-merge off | **Partially.** No open PR has auto-merge enabled (verified 2026-11-08), but nothing prevents enabling it per PR. |
| Four simultaneous requests / two automation slots | **No (policy only).** The four-session figure is provider-reported (ISU interview 2026-10-26) and its scope is unconfirmed; no limiter exists in this project. The live app's per-minute cap (`api/ai_routes.py`) is a different thing: it limits public calls to the deployed site, not agent concurrency. |
| Subagents prohibited | **No technical enforcement.** The prohibition is instruction-only for now; bounded mode is planned only after a shared limiter exists. |
| AI review satisfies GitHub required approvals | **No.** AI verdicts are evidence only. A required approval must come from an eligible non-author account (a separate human, or an appropriately configured bot); the PR author — often the owner's account — cannot approve their own PR. |
| Traceability and math rules | **Partially.** Code-enforced where implemented (quote verification, unit tests, live checks in CI); otherwise instruction plus reviewer judgment. |

To make the Git rules real: add a branch protection rule on `main` (require a pull request with one review, no direct pushes, no force pushes) and leave auto-merge disabled in the repository settings. Until that is done, treat "no direct pushes to main" as a promise, not a guarantee.

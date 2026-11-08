# Local setup checkpoint — 2026-11-08

This checkpoint supersedes earlier installation-status notes in AGENT_WORKFLOW.md.

- Setup and quickstart are PRs #33 and #34. Lifecycle review and Windows/Linux CI passed. Live Codex/OpenCode workers are now authorized and enabled, initially two at a time.
- Codex CLI: installed and authenticated with ChatGPT.
- Claude Code CLI: 2.1.319 installed and authenticated. Usage temporarily paused at the owner's request (91% weekly usage); no automatic fallback to Claude.
- GitHub CLI: installed and authenticated.
- Python environment: .venv; API requirements plus pytest installed; pip check passed.
- Controller: 29 offline tests passed on Windows, including contained descendants and abrupt controller termination. Codex and standalone ISU OpenCode are enabled; Claude remains blocked. Independent runtime-enablement review found no blockers.
- API: 127 tests passed, 3 deprecation warnings. Windows uses spawn when fork is unavailable; Linux retains fork. Added real child-process result/error/timeout tests and made existing fixtures portable.
- Web: locked dependencies installed. npm run build -- --webpack passed. Default Turbopack build crashes locally even outside the restricted execution environment; unresolved.
- Worker-produced website PR #35 (latest ticker request wins) passed 13 tests, a build and independent review, then merged under Jacob's authorization. Vercel reports production deployment success. No financial formulas changed.

Next: finish the queued CSV-export feature and review/test it before PR completion. Windows kill-on-close Job Objects and conservative recover are active. Unsupported platforms refuse real dispatch; legacy/uncertain owners refuse recovery. Workers never self-merge; the supervisor completes eligible PRs after checks/review. Claude usage remains paused, including fallback.

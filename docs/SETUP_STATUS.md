# Local setup checkpoint — 2026-11-08

This checkpoint supersedes earlier installation-status notes in AGENT_WORKFLOW.md.

- Setup and quickstart are draft PRs #33 and #34. Lifecycle hardening is being reviewed on a separate local worktree.
- Codex CLI: installed and authenticated with ChatGPT.
- Claude Code CLI: 2.1.319 installed and authenticated. Usage temporarily paused at the owner's request (91% weekly usage); no automatic fallback to Claude.
- GitHub CLI: installed and authenticated.
- Python environment: .venv; API requirements plus pytest installed; pip check passed.
- Controller: 29 offline tests passed on Windows, including real contained fixture descendants and abrupt controller termination. All live adapters remain disabled.
- API: 127 tests passed, 3 deprecation warnings. Windows uses spawn when fork is unavailable; Linux retains fork. Added real child-process result/error/timeout tests and made existing fixtures portable.
- Web: locked dependencies installed. npm run build -- --webpack passed. Default Turbopack build crashes locally even outside the restricted execution environment; unresolved.
- Draft branches are pushed; nothing merged to main or deployed to production. No financial methods changed.

Next: finish independent review and Windows/Linux CI for lifecycle hardening. Windows kill-on-close Job Objects, durable owner identity, additive SQLite migration, and explicit conservative recover CLI passed the supervisor's native test run. Unsupported platforms refuse real dispatch; legacy/uncertain owner identities refuse recovery. Live provider adapters remain disabled pending a separate supervised end-to-end trial. Claude usage remains paused.

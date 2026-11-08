# Local setup checkpoint — 2026-11-08

This checkpoint supersedes earlier installation-status notes in AGENT_WORKFLOW.md.

- Branch: setup/agent-workflow. Changes remain local and uncommitted.
- Codex CLI: installed and authenticated with ChatGPT.
- Claude Code CLI: 2.1.319 installed and authenticated. Usage temporarily paused at the owner's request (91% weekly usage); no automatic fallback to Claude.
- GitHub CLI: installed and authenticated.
- Python environment: .venv; API requirements plus pytest installed; pip check passed.
- Controller: 15 offline tests passed. All live adapters remain disabled.
- API: 127 tests passed, 3 deprecation warnings. Windows uses spawn when fork is unavailable; Linux retains fork. Added real child-process result/error/timeout tests and made existing fixtures portable.
- Web: locked dependencies installed. npm run build -- --webpack passed. Default Turbopack build crashes locally even outside the restricted execution environment; unresolved.
- Nothing pushed, merged, or deployed. No financial methods changed.

Next: run a supervised Codex builder/OpenCode reviewer trial before enabling automatic dispatch. Windows process-tree cleanup and interrupted-job recovery remain unresolved controller limitations.

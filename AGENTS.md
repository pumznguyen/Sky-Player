# Project Rules

This is a Windows 11 Sky music playback helper.

Hard constraints:
- Do not modify game files.
- Do not read game memory.
- Do not bypass anti-cheat or security systems.
- Use Windows SendInput only.
- Preserve current CLI behavior unless explicitly changed.
- Prioritize timing correctness, testability, and strict validation.
- Avoid broad rewrites without tests.

Coding rules:
- Python 3.11+.
- Type hints required.
- Prefer dataclass(frozen=True, slots=True) for domain models.
- Avoid globals in new code.
- Scheduler must be pure and unit-testable.
- Windows backend must be isolated behind an interface.

Workflow rules:
- Use `uv run <command>` for all Python executions (run, test, lint, typecheck).
- Do NOT use `pip install` inside .venv; use `uv add <package>` or `uv add --dev <package>`.
- Use `uv sync` to install/update project dependencies.
- Do NOT manually activate .venv in scripts or CI; `uv run` handles it.

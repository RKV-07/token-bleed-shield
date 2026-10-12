# RFC 0001: Pre-Flight Environment Pinning Contract (`.agent-env.md`)

- **Status**: Draft
- **Authors**: asinfer team
- **Target**: Coding Agents (Claude Code, Cursor, Antigravity, Windsurf, Aider, Devin)

---

## 1. Abstract

When autonomous coding agents are initialized in a software project, they lack ground-truth knowledge of the host execution environment. As a consequence, models routinely issue exploratory commands (e.g. `which python`, `where pip`, `python -m venv`, `cat package.json`) or attempt invalid commands based on wrong assumptions (e.g. executing `python main.py` in a repository managed strictly via `uv run main.py`).

This RFC proposes a standardized specification for `.agent-env.md`, an immutable environment contract generated via static pre-flight probes before agent sessions begin.

---

## 2. Specification

An `.agent-env.md` file MUST be located in the workspace root directory. It contains machine-actionable markdown blocks containing:

1. **Host Environment**: Operating system, primary shell, architecture.
2. **Pinned Toolchains**: Explicit binaries, package managers, and command prefixes.
3. **Execution Rules**: Explicit `ALLOW` and `DISALLOW` commands.
4. **Project Boundaries**: Root paths, source paths, test commands.

### Example Contract

```markdown
<!-- TOKEN-BLEED-SHIELD-CONTRACT-V1 -->
# AGENT RUNTIME CONTRACT

## Host
- OS: Windows 11
- Shell: PowerShell 7 (`pwsh`)
- Workspace Root: `C:\Users\PRANAV PATIL\token-bleed-shield`

## Pinned Toolchains
- Python Manager: `uv` (v0.6.2)
  - Execute scripts: `uv run <script>`
  - Add packages: `uv add <package>`
  - Install dev: `uv pip install -e .`
  - FORBIDDEN: Do NOT invoke `python`, `pip`, or `python3` directly.
- Node.js Manager: `pnpm` (v9.1.0)
  - Run scripts: `pnpm run <script>`
  - FORBIDDEN: Do NOT invoke `npm` or `yarn`.

## Pre-flight Disclaimers
1. Do not scan directories for runtime binaries.
2. Rely strictly on pinned command prefixes.
3. Do not explore parent directories outside workspace root.
```

---

## 3. Benefits

- **Token Elimination**: Avoids 5 to 15 exploratory tool round-trips during session boot.
- **Error Elimination**: Zero failed shell executions caused by missing virtual environment activations.
- **Determinism**: Same commands executed regardless of model stochasticity.

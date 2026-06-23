# Brigade Gateway — Claude Subagent Roles

This project uses a multi-agent swarm. Each subagent owns a distinct concern; agents do not edit each other's files without explicit handoff.

## Subagents

| Role | Stub file | Responsibility |
|---|---|---|
| **planner** | `agents/planner.md` | Breaks down PRD milestones into task lists; owns the task backlog; resolves cross-agent conflicts. |
| **builder-pipeline** | `agents/builder-pipeline.md` | Implements the pipecat pipeline (`app/pipeline.py`, `app/services/`): VAD, STT, LLM, TTS, tool functions, guardrails. |
| **builder-data** | `agents/builder-data.md` | Owns database layer (`app/db/`, `db/schema.sql`): Supabase client, `leads` and `human_followup` writes, migration scripts. |
| **builder-server** | `agents/builder-server.md` | Owns FastAPI server (`app/server.py`), WebRTC signalling endpoint, static file serving, startup/shutdown hooks. |
| **verifier** | `agents/verifier.md` | Runs tests (`tests/`), checks Phase 0 DoD checklist, reports failures to planner; does not modify `app/`. |
| **simplifier** | `agents/simplifier.md` | Refactors for clarity, removes dead code, enforces style (ruff); only acts after verifier passes. |

## Conventions

- Each agent reads `app/config.py` for canonical env var names; never hard-code secrets.
- builder-pipeline and builder-server coordinate on the FastAPI `app` object — agree on the module boundary in `app/server.py` vs `app/pipeline.py` before editing.
- verifier runs `pytest tests/` and the Phase 0 browser smoke-test checklist before signing off on any milestone.

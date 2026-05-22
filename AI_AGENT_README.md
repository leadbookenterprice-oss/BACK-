# Leadbook - AI Agent Operating Guide

This repo is part of the Leadbook multi-agent workspace. OpenCode, Codex, Antigravity, and other AI agents must follow the same workflow to avoid overwriting each other.

The live collaboration file is:

`AI_COLLABORATION_LOG.md`

If working in the local `new leadbook` folder, also read the parent-level files:

- `..\README.md`
- `..\AI_COLLABORATION_LOG.md`

## Goal

- Keep all AI agents moving in the same direction.
- Make every change auditable.
- Avoid duplicate work and accidental reversions.
- Preserve frontend, backend, admin, Railway, Cloudinary, and worker architecture decisions.

## Required Workflow

1. Read `AGENTS.md`.
2. Read `AI_AGENT_README.md`.
3. Read `AI_COLLABORATION_LOG.md`.
4. Inspect repo state with `git status -sb`.
5. Inspect local changes with `git diff`.
6. Inspect recent history with `git log --oneline -10`.
7. Make the smallest correct change.
8. Run relevant verification.
9. Stage only files related to the task.
10. Update `AI_COLLABORATION_LOG.md` before closing the task.

## No-Pisarse Rules

- Do not revert changes you did not make.
- Do not overwrite another agent's work.
- Do not assume modified files are safe to edit.
- If unrelated files are dirty, ignore them.
- If your task conflicts with existing changes, ask before proceeding.
- Do not force push or use destructive resets.

## Audit Workflow

Audits must follow the same direction:

- Read coordination files first.
- Review branch, status, diff, and recent commits.
- Do not modify code during the first audit pass.
- Report findings by severity with file/line references.
- If fixes are authorized, apply minimal changes and verify.
- Register audit findings and fixes in `AI_COLLABORATION_LOG.md`.

## Technical Decisions To Preserve

- Cloudinary stores media/files.
- Postgres/SQL stores only URLs and lightweight metadata.
- No base64, videos, audios, PDFs, or heavy HTML in SQL/Postgres.
- Web/API should not render heavy videos inside normal requests.
- API enqueues video; worker processes it.
- Video priority: `business` > `scale` > `pro` > `starter`.
- Valid visible plan names: `Starter`, `Pro`, `Scale`, `Business`.
- Do not use `Free` or `Starter Free`.
- Production must use `ALLOW_GLOBAL_API_FALLBACK=False`.
- Recommended/default production video provider: `leadbook_sync`.
- Missing API assignment should show an API/pool error, not a credits exhausted error.

## Backend Notes

- Work in this repo for API, Railway, migrations, workers, queues, and integrations.
- Verify backend changes with `py -3 manage.py check` when feasible.
- Check migrations with `py -3 manage.py makemigrations --check --dry-run` when models change.
- Keep video queue and worker processing separate from web request handling.
- Do not store media-heavy payloads in Django models/Postgres.

## Startup Prompt

```text
You are working on Leadbook with multiple AI agents. Before modifying anything:

1. Read `AGENTS.md`, `AI_AGENT_README.md`, and `AI_COLLABORATION_LOG.md`.
2. If available locally, read `../README.md` and `../AI_COLLABORATION_LOG.md`.
3. Summarize the current context in 5 lines and list files/areas you must not overwrite.
4. Run `git status -sb`, review `git diff`, and inspect `git log --oneline -10`.
5. Do not revert or overwrite unrelated work.
6. Make the smallest correct change and verify it.
7. Update `AI_COLLABORATION_LOG.md` before finishing.
```

## Closing Prompt

```text
Before closing, update `AI_COLLABORATION_LOG.md` with date, agent, objective, files modified, changes made, verification commands/results, commit/push, and pending risks.
```

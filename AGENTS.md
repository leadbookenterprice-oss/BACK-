# Agent Instructions - Leadbook Backend

Before modifying this repository, read:

1. `AI_AGENT_README.md`
2. `AI_COLLABORATION_LOG.md`
3. If present locally, `..\README.md` and `..\AI_COLLABORATION_LOG.md`

Mandatory rules:

- Check `git status -sb`, `git diff`, and `git log --oneline -10` before edits.
- Do not revert, delete, or overwrite work from another agent or the user.
- Stage and commit only files related to your task.
- If you find unrelated local changes, leave them untouched.
- If there is a conflict or ambiguity, stop and ask.
- After finishing, update `AI_COLLABORATION_LOG.md` with files touched, verification, commit/push, pending risks, and agent name.

Architecture rules:

- Cloudinary stores media/files.
- Postgres stores only URLs and lightweight metadata.
- Do not store base64, videos, audios, PDFs, or heavy HTML in SQL/Postgres.
- Web/API should enqueue video; worker processes video.
- Valid plan names: `Starter`, `Pro`, `Scale`, `Business`.
- Do not use `Free` or `Starter Free`.
- Production must use `ALLOW_GLOBAL_API_FALLBACK=False`.

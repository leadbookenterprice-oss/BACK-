# AI Collaboration Log - Leadbook

This file is the repo-local collaboration log for Leadbook agents.

If working in the local `new leadbook` workspace, also read and update the parent-level `..\AI_COLLABORATION_LOG.md` when possible.

Add new entries at the top of the Agent Log section.

## Mandatory Rules

1. Read this file before modifying code.
2. Check `git status -sb`, `git diff`, and `git log --oneline -10` first.
3. Do not revert, delete, or overwrite changes from another agent or the user.
4. If there is a conflict, stop and ask.
5. Register what you changed, what you verified, commit/push status, and pending risks.
6. Cloudinary stores media/files; Postgres stores only URLs/metadata.
7. Do not store base64, videos, audios, PDFs, or heavy HTML in SQL/Postgres.
8. Web/API enqueues video; worker processes it.
9. Valid plan names: `Starter`, `Pro`, `Scale`, `Business`.
10. Production must use `ALLOW_GLOBAL_API_FALLBACK=False`.

## Project Map

- Local workspace root: `C:\Users\elalc\Desktop\desk\new leadbook`
- Frontend repo: `frontend-master`
- Backend/API/Railway repo: `Backend--main`
- Admin repo: `dash_admin_leadbook-master`
- Production frontend: `https://leadbook.com.ar`
- Production backend: `https://backend-production-1fefc.up.railway.app`
- Correct admin: `https://dash-admin-leadbook.vercel.app`

## Current Direction

- `leadbook_sync` is the recommended/default production video provider.
- Video should be queued by plan priority: `business` > `scale` > `pro` > `starter`.
- Video should enqueue during initial listing generation, not only when opening the Video tab.
- Frontend should send uploaded Cloudinary URLs, not base64, to backend.
- Missing API assignment should show API/pool repair messaging, not credits exhausted.
- Production video mode should use Celery/worker, not web request rendering.

## Last Known Frontend State

- Branch: `master`
- Last known pushed commit before this coordination update: `30f57d5 fix(listings): improve media previews and video queue`
- Recent verified command: `npm run build` OK.

Recent frontend changes:

- `src/components/steps/Step06.jsx`
- Portada preview constrained to a reasonable vertical 9:16 card.
- Recorrido photos no longer go through cropper.
- Recorrido previews use `object-contain` to avoid stretching/cropping cars/interiors.
- Dead crop queue logic removed.
- `src/pages/ResultadosPage.jsx`
- Added `videoFormData` after photo upload/cleanup.
- `TabVideo` receives cleaned form data.
- Video auto-enqueues from initial listing generation.
- Initial overlay includes `Video` as the sixth format.

## Last Known Backend State

Relevant known commits:

- `b375728 fix(api): repair pool setup and media storage`
- `03a269e feat: notify admin on trial token requests`
- `7bad69e feat(video): add prioritized video queue`

Recent backend changes known:

- Migration `api/migrations/0015_services_pool_and_media_cleanup.py` created.
- Base services created: `gemini`, `elevenlabs`, `uploadpost`, `cloudinary`.
- Env keys imported where present.
- Available keys assigned/repaired for active users.
- Base64/data URLs cleaned from profile/listing fields.
- `APIKeyUnavailableError` separated from quota exhaustion.
- `api_key_unavailable` returns `503`.

## Agent Log

### 2026-05-22 - OpenCode - Add multi-agent coordination files to repos

Objective:

- Push coordination instructions into the Git repositories so all AI agents can read them from GitHub.

Files modified:

- `AGENTS.md`
- `AI_AGENT_README.md`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added mandatory workflow, anti-overwrite rules, audit workflow, architecture decisions, startup prompt, and closing prompt.
- Added repo-local collaboration log with current project direction and recent known state.

Verification:

- Docs-only change. No backend check required.
- Repo status reviewed before staging.

Commit/push:

- Included in commit `docs(ai): add multi-agent coordination guide`.

Pending/risks:

- Keep this file updated after every agent session.
- If multiple repo-local copies diverge, prefer the newest timestamped entry and mirror important context across repos.

## Global Pending Items

- Browser-test `/nuevo`: upload photos, confirm previews, generate listing, verify automatic video enqueue.
- Confirm Railway migration `0015` is applied.
- Confirm API pool has real keys.
- Confirm Celery worker active with `APP_ROLE=worker` and `REDIS_URL`.
- Confirm production has `ALLOW_GLOBAL_API_FALLBACK=False`.

## New Entry Template

```markdown
### YYYY-MM-DD - AGENT - SHORT TITLE

Objective:

- ...

Files modified:

- `path/to/file`

Changes made:

- ...

Verification:

- `command` OK/FAILED

Commit/push:

- `hash message` or `no commit`

Pending/risks:

- ...
```

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

### 2026-05-28 - Antigravity - Fix onboarding 400 errors on agentes-comerciales creation

Objective:

- Fix HTTP 400 errors during onboarding when frontend POST to `/api/auth/agentes-comerciales/` fails repeatedly with "Error al crear agente comercial".

Files modified:

- `api/views.py`

Changes made:

- **OnboardingView**: Auto-creates a default `ComercialAgentProfile` from user data (nombre, email, telefono, logo_url) if none exists after saving user fields. Handles `IntegrityError` gracefully for race conditions.
- **commercial_agents_collection POST**: Added flexible field name mapping (name→nombre, phone→telefono_e164, etc.) so frontend variants are accepted. Default `nombre` to user's name when missing. Wrapped creation in `transaction.atomic()`. Added `IntegrityError` handling for the `unique_default_commercial_agent_per_owner` constraint — retries creation without `is_default` if constraint is violated.

Verification:

- `python -m py_compile api/views.py` OK.

Commit/push:

- No commit.

Pending/risks:

- If the frontend still sends POST to `/api/auth/agentes-comerciales/` after onboarding creates the default profile, it may create a duplicate (non-default) agent. Frontend should check if `default_agent` is already returned from onboarding before creating another.
- Deploy to production to apply the fix.

### 2026-05-25 - OpenCode - Added five softer templates and backend file mapping

Objective:

- Expand template catalog with softer Mediterranean-style variants while keeping generation stable for all formats.

Files modified:

- `api/views.py`

Changes made:

- Added 5 new system templates to `TEMPLATE_IDS` and `TEMPLATE_CATALOG`: `costa_serena`, `oliva_natural`, `terracota_suave`, `brisa_calida`, `arena_clara`.
- Added palette/font metadata for each new template so they appear differentiated in catalog and token system.
- Added `TEMPLATE_FILE_BASE` alias mapping so these new templates reuse the existing `mediterraneo` HTML files for post/story/carrusel/email.
- Updated template-to-file maps (`TEMPLATE_POST_MAP`, `TEMPLATE_STORY_MAP`, `TEMPLATE_CAROUSEL_MAP`, `TEMPLATE_EMAIL_MAP`) to resolve aliases safely.
- Updated `_default_tokens_for_base_template` style/image maps to classify new templates under `mediterranean_warm` + `warm` treatment.

Verification:

- `python -m py_compile api/views.py` OK.

Commit/push:

- No commit.

Pending/risks:

- New templates are visually differentiated via tokens/colors/fonts but currently share mediterraneo structural HTML; fully unique composition requires dedicated template files.

### 2026-05-25 - OpenCode - Professional video quality pass (voice, captions, mix)

Objective:

- Raise perceived production quality of generated videos with clearer narration, stronger subtitle treatment, and more polished default render profile.

Files modified:

- `api/services/lightweight_video_service.py`

Changes made:

- Updated `IG_PRO_MAX` defaults to a more stable premium profile (`1080x1920`, `30fps`, `crf=18`, `preset=medium`, `max_photos=8`).
- Improved voice chain in audio mix with speech-focused processing (`highpass`, `lowpass`, stronger compression, de-esser, higher default voice gain).
- Rebalanced bed/music defaults to keep narration intelligible (lower default music level, stronger voice presence).
- Added final loudness mastering stage (`loudnorm`) after limiter for more consistent playback loudness across outputs.
- Upgraded caption visual defaults (larger size, better outline opacity/weight, adjusted bottom margin, stronger background alpha).
- Added ASS subtitle generation from timed caption chunks with fade-in/fade-out per cue, then burn via ASS path for more professional subtitle motion.
- Kept resilient fallback path: ASS burn -> SRT burn -> drawtext fallback if needed.

Verification:

- `python -m py_compile api/services/lightweight_video_service.py` OK.

Commit/push:

- No commit.

Pending/risks:

- Exact subtitle font fidelity still depends on runtime availability/configuration of `LIGHT_VIDEO_CAPTION_FONT_FILE`.
- `loudnorm` and ASS rendering require ffmpeg builds with expected filters/libass support in production image.

### 2026-05-24 - OpenCode - ElevenLabs narration and music variety improvements

Objective:

- Ensure narration uses ElevenLabs when available and improve background music variety from `musica_videos`.

Files modified:

- `api/services/lightweight_video_service.py`

Changes made:

- Extended voice generation flow to return voice engine diagnostics (`elevenlabs`, `flite_fallback`, `none`) plus error reason.
- Persisted narration metadata (`video_voice_engine`, `video_voice_error`) in listing data for easier debugging in production.
- Kept ElevenLabs as primary narration path and fallback to local flite only when ElevenLabs is unavailable/rate-limited and fail-open is active.
- Expanded music discovery to scan multiple audio formats (`mp3`, `wav`, `m4a`, `aac`, `ogg`) and nested folders under `musica_videos`.
- Improved music variation by selecting tracks deterministically per generation ID when available, avoiding same-track repetition across regenerations.

Verification:

- `python -m py_compile api/services/lightweight_video_service.py` OK.

Commit/push:

- No commit.

Pending/risks:

- If ElevenLabs credentials are blocked in provider account, fallback voice can still be used but premium voice quality depends on restoring ElevenLabs access.

### 2026-05-24 - OpenCode - Regeneration uniqueness hardening

Objective:

- Ensure each video regeneration produces a fresh generation cycle and not a visually identical cached outcome.

Files modified:

- `api/services/video_queue.py`
- `api/services/lightweight_video_service.py`
- `api/views.py`

Changes made:

- Added `generation_id` when enqueueing each video request.
- Updated `leadbook_sync` script variant seed to include `generation_id` so repeated regenerations rotate template variants reliably.
- Persisted `video_generation_id` in listing metadata after successful render.
- Exposed `video_version` in `video_status` response to support stronger cache busting in frontend.

Verification:

- `python -m py_compile api/services/video_queue.py api/services/lightweight_video_service.py api/views.py` OK.

Commit/push:

- No commit.

Pending/risks:

- If user-provided scenes are fixed and exhaustive, script text will still stay close to source text by design.

### 2026-05-24 - OpenCode - Image quality and Jost captions refinement

Objective:

- Preserve source image quality in generated videos and improve caption rendering quality/line wrapping with the requested professional typography.

Files modified:

- `api/services/lightweight_video_service.py`
- `.env.example`

Changes made:

- Increased intermediate image encoding quality (`LIGHT_VIDEO_IMAGE_QUALITY`, JPEG quality 96 + subsampling 0) to avoid visible degradation.
- Simplified zoompan chain to avoid extra pre-scale pass that could soften frames.
- Added caption font resolver with optional `LIGHT_VIDEO_CAPTION_FONT_FILE` support; default family now `Jost`.
- Added caption wrapping (`LIGHT_VIDEO_CAPTION_MAX_CHARS_PER_LINE`) to reduce broken/cut words.
- Applied wrapping to both SRT burn path and drawtext fallback path.
- Added optional fontsdir injection for libass subtitle rendering when a font file path is provided.

Verification:

- `python -m py_compile api/services/lightweight_video_service.py` OK.

Commit/push:

- No commit.

Pending/risks:

- To guarantee Jost in production, set `LIGHT_VIDEO_CAPTION_FONT_FILE` to a real `.ttf` path available inside the runtime container.

### 2026-05-24 - OpenCode - Persist generated listing assets

Objective:

- Fix historical listings so opening them uses saved Cloudinary URLs/results instead of losing cached generated assets and forcing regeneration.

Files modified:

- `api/views.py`
- `api/tests.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Updated listing data merging to preserve existing `datos_extra.resultados` when frontend sends cleaned listing data without generated results.
- Deep-merge incoming partial `resultados` with existing results so one format update does not delete other generated formats.
- Added `formatos_generados` to listing list/detail responses, derived from persisted results and video state.
- Updated PDF download behavior to prefer saved Cloudinary PDF URLs before falling back to legacy HTML render.
- Added tests covering result preservation and PDF streaming from a saved Cloudinary URL.

Verification:

- `py -3 -m py_compile api/views.py api/tests.py` OK.
- `py -3 manage.py test api.tests.ListingResultPersistenceTests` OK.
- `py -3 manage.py check` OK.
- `git diff --check` OK, only expected CRLF/LF warning on Windows.

Commit/push:

- Included in the 2026-05-24 push request to `origin/main`; final commit hash reported in chat.

Pending/risks:

- Existing rows that already lost `datos_extra.resultados` cannot be recovered from Postgres alone; recover from Cloudinary by listing per-user/listing prefixes if needed.
- Concurrent unrelated backend edits were present during final status (`api/plan_utils.py`, `api/views_crm.py`, and Pro-feature decorators in `api/views.py`); they were not reverted.

### 2026-05-24 - OpenCode - Sales script and stable motion pass

Objective:

- Make `leadbook_sync` scripts more sales-focused and data-driven, diversify script structure, remove shaky motion, and improve caption readability.

Files modified:

- `api/services/lightweight_video_service.py`
- `.env.example`

Changes made:

- Reworked `_build_voice_script` with 4 sales-oriented variants selected deterministically per listing.
- Added property-type buckets (`terreno`, `cochera`, `oficina`, `local`, `departamento`, `residencial`) so script focus changes by asset type.
- Prioritized user-provided listing data (operation, city, price, bedrooms, baths, parking, surfaces, amenities) in script assembly.
- Added `LIGHT_VIDEO_SIMPLE_ZOOM_ONLY` and defaulted motion to smooth zoom-only (`in`) to eliminate shake-like drift behavior.
- Increased caption default size slightly and switched default font to a more professional sans-serif for better readability.

Verification:

- `python -m py_compile api/services/lightweight_video_service.py` OK.

Commit/push:

- No commit.

Pending/risks:

- If tone needs stronger urgency, tweak template strings in `_build_voice_script` and keep character limits aligned with max duration.

### 2026-05-23 - OpenCode - Leadbook Sync audio and captions hardening

Objective:

- Fix missing voiceover and missing burned captions in `leadbook_sync` videos while keeping queue + storage safety.

Files modified:

- `api/services/lightweight_video_service.py`
- `.env.example`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added local TTS fallback for `leadbook_sync` using FFmpeg `flite` when ElevenLabs is unavailable/exhausted and fail-open is active.
- Added optional force-voiceover mode (`LIGHT_VIDEO_FORCE_VOICEOVER`) for cases where listings are arriving with `voiceover=false` unexpectedly.
- Added drawtext caption fallback: if ASS/libass subtitle burn fails, backend retries caption burn with FFmpeg `drawtext` using timed chunks.
- Extended caption metadata to include timed chunks for fallback rendering.
- Documented new env knobs for TTS fallback and caption fallback.

Verification:

- `python -m py_compile api/services/lightweight_video_service.py api/tasks.py api/views.py` OK.
- `git diff -- api/services/lightweight_video_service.py .env.example` reviewed.

Commit/push:

- No commit.

Pending/risks:

- `flite` voice quality is less natural than ElevenLabs; treat as resilience fallback, not premium default.
- Drawtext fallback depends on FFmpeg `drawtext` availability in runtime image; if missing, captions still degrade gracefully to no-burn.

### 2026-05-23 - OpenCode - Leadbook Sync quality upgrade

Objective:

- Keep `leadbook_sync` as the primary video provider and improve visual quality to get closer to HyperFrames style without reintroducing storage overload risks.

Files modified:

- `api/services/lightweight_video_service.py`
- `api/tasks.py`
- `api/views.py`
- `.env.example`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Set backend defaults back to `leadbook_sync` for queue dispatch and provider resolution.
- Upgraded `leadbook_sync` render pipeline with optional cinematic transitions between scenes using FFmpeg `xfade` with safe fallback to classic concat.
- Added configurable film-look pass (contrast/saturation/brightness/gamma/sharpen/optional denoise) applied in segment rendering.
- Tuned runtime quality guard defaults to allow better vertical resolution while keeping safety bounds for constrained workers.
- Added env knobs for transitions/look/runtime guard to tune quality without code changes.
- Kept queue architecture and DB-safety protections intact (no base64/data URI persistence changes were reverted).

Verification:

- `python -m py_compile api/services/lightweight_video_service.py api/tasks.py api/views.py` OK.
- `git diff -- api/services/lightweight_video_service.py api/tasks.py api/views.py .env.example` reviewed.

Commit/push:

- No commit.

Pending/risks:

- Visual transitions increase encode complexity; if worker pressure rises, reduce `LIGHT_VIDEO_TRANSITION_SECONDS` and/or disable transitions.
- Keep `VIDEO_QUEUE_MAX_ACTIVE=1` and monitor worker memory during rollout.

### 2026-05-23 - OpenCode - HyperFrames primary with safe failover

Objective:

- Recover the previous HyperFrames visual result while keeping anti-overload protections for Postgres and production stability.

Files modified:

- `api/tasks.py`
- `api/views.py`
- `.env.example`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Switched default provider resolution to `hyperframes` in queue dispatch and task defaults.
- Added provider failover logic in `api/tasks.py`: if HyperFrames fails, worker can retry with `leadbook_sync` (controlled by env vars).
- Added env toggles `VIDEO_PROVIDER_FAILOVER_ENABLED` and `VIDEO_PROVIDER_FAILOVER_TARGET` to make failover explicit/configurable.
- Kept queue/worker architecture and did not touch payload sanitization/base64 rejection rules that protect Postgres from JSON bloat.

Verification:

- `python -m py_compile api/tasks.py api/views.py` OK.
- `python manage.py check` FAIL in local env: `ModuleNotFoundError: No module named 'playwright'` (pre-existing environment dependency issue, unrelated to this patch logic).
- `git diff -- api/tasks.py api/views.py .env.example` reviewed.

Commit/push:

- No commit.

Pending/risks:

- In production, set `VIDEO_PROVIDER=hyperframes` and keep `VIDEO_PROVIDER_FAILOVER_ENABLED=True` to preserve quality with automatic fallback.
- HyperFrames resource limits (`HYPERFRAMES_BROWSER_GPU_MODE=software`, workers/quality) must stay tuned to avoid render failures on Railway.

### 2026-05-22 - OpenCode - Notification mojibake repair helper

Objective:

- Diagnose why notification text renders as `estÃ...` and add the missing backend helper required to repair mojibake when notifications are created/listed.

Files modified:

- `api/utils.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Confirmed the visual issue is mojibake: UTF-8 Spanish text was previously stored/rendered after being decoded as Windows-1252/Latin-1.
- Added `repair_mojibake_text` in `api/utils.py`, covering common double/triple-encoded Spanish accent sequences and falling back to `ftfy.fix_text`.
- Updated `crear_notificacion` to normalize notification title/message before saving future rows.
- The current `api/views.py` HEAD already calls `repair_mojibake_text` when listing notifications, so existing stored broken rows are repaired on response after this helper exists.

Verification:

- `py -3 -m py_compile api/views.py api/utils.py` OK.
- `py -3 manage.py check` OK.
- `git diff --check` OK.

Commit/push:

- Included in commit `fix(api): repair notification mojibake` and pushed to `origin/main`.

Pending/risks:

- Deploy backend so production uses the helper.
- Existing DB rows remain physically mojibaked, but API responses should render clean; run a one-off DB cleanup later if desired.

### 2026-05-22 - OpenCode - CRM V1 pipeline and Meta leads

Objective:

- Implement CRM V1 backend for "ningun lead se queda en visto": pipeline, lead dedupe, Meta webhook ingest, SLA follow-up tasks, timeline and metrics.

Files modified:

- `api/models.py`
- `api/serializers.py`
- `api/services/crm_service.py`
- `api/views_crm.py`
- `api/urls.py`
- `api/migrations/0016_lead_pipelinestage_leadevent_leadassignment_and_more.py`
- `api/tests_crm.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added CRM models: `PipelineStage`, `Lead`, `LeadEvent`, `LeadAssignment`, `FollowUpTask`.
- Added default pipeline stages: `nuevo`, `contactado`, `calificado`, `visita`, `cierre`, `perdido`.
- Added lead creation/dedupe service using `leadgen_id` first, then contact + listing + time window.
- Added initial high-priority follow-up task and SLA due date on new lead creation.
- Added endpoints under `/api/auth/crm/` for pipeline, leads, move stage, mark contacted, task update and metrics.
- Added Meta Leads webhook at `/api/crm/meta/webhook/` with verification, optional signature validation, idempotent ingest and `soft_rate_limited` retry contract.
- Added CRM tests for dedupe, initial follow-up, stage transition timeline, contact completion, webhook idempotency and soft rate limit contract.

Verification:

- `py -3 manage.py makemigrations api` OK, generated migration `0016`.
- `py -3 manage.py makemigrations --check --dry-run` OK.
- `py -3 manage.py check` OK.
- `py -3 manage.py test api.tests_crm` OK, 6 tests.
- `git diff --check -- api/models.py api/serializers.py api/services/crm_service.py api/views_crm.py api/urls.py api/tests_crm.py api/migrations/0016_lead_pipelinestage_leadevent_leadassignment_and_more.py` OK.

Commit/push:

- No commit.

Pending/risks:

- Apply migration `0016` in deployment.
- Configure production env: `CRM_META_VERIFY_TOKEN`, `META_APP_SECRET`, `CRM_META_DEFAULT_OWNER_ID` or robust page-to-owner mapping, plus Meta access token source for lead detail fetch.
- Browser/API-test Meta webhook with a real test lead.
- Existing unrelated dirty files (`api/views.py`, `api/tests.py`, `api/services/almacenamiento.py`, extractor/ads files) were not reverted or overwritten.

### 2026-05-22 - OpenCode - Ads Studio V1 and URL extraction

Objective:

- Add acquisition workflow support: property URL extraction plus Meta Ads variant generation, exportable/reusable by listing.

Files modified:

- `api/services/listing_extractor.py`
- `api/services/ads_studio.py`
- `api/views.py`
- `api/urls.py`
- `api/tests.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added secure HTML/JSON-LD property extractor with SSRF host validation, bounded downloads, structured extraction and semistructured fallback.
- Added `POST /api/listados/extract-from-url/` returning normalized listing data, confidence and warnings.
- Added Ads Studio service helpers and `POST /api/ads/generate-meta-variants/` using the existing Gemini/API pool path via `smart_call`.
- Added soft/hard quota handling for Ads Studio responses and traceable `[ADS_STUDIO]` logs.
- Persisted generated ad variants under `Listado.datos_extra.resultados.meta_variants` without schema migration.
- Added backend tests for structured extraction, fallback extraction, controlled extractor error, endpoint integration, persistence, soft rate limit and hard quota.

Verification:

- `py -3 -m py_compile api/services/listing_extractor.py api/services/ads_studio.py api/views.py api/urls.py api/tests.py` OK.
- `py -3 manage.py test api.tests.ListingExtractorTests api.tests.AdsStudioEndpointTests` OK.
- `py -3 manage.py check` OK.
- `py -3 manage.py test api` OK.
- `py -3 manage.py makemigrations --check --dry-run` OK.
- `git diff --check` OK, only LF/CRLF warning.

Commit/push:

- No commit.

Pending/risks:

- Concurrent unrelated backend changes appeared during the session (`api/models.py`, `api/serializers.py`, `api/views_crm.py`, CRM migration and service). They were not reverted.
- Real portal scraping needs manual validation because JS-rendered or blocked pages may return low confidence/fallback-only data.

### 2026-05-22 - OpenCode - Security hardening pass

Objective:

- Apply defensive security fixes across backend/admin auth, secrets exposure, webhooks, debug endpoints, OTP logs, WebSockets, render/video SSRF, and production env defaults.

Files modified:

- `subzero_core/settings.py`
- `admin_panel/consumers.py`
- `admin_panel/views.py`
- `admin_panel/views_cloudinary.py`
- `api/admin.py`
- `api/consumers.py`
- `api/services/gemini_video_service.py`
- `api/services/lightweight_video_service.py`
- `api/services/render_engine.py`
- `api/tasks.py`
- `api/views.py`
- `api/views_admin.py`
- `.env.example`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added `ALLOW_ADMIN_KEY_AUTH` and `ALLOW_DEBUG_ENDPOINTS`, both defaulting to `DEBUG`/false in production examples.
- Removed broad CORS regexes and only allows `x-admin-key` when emergency admin key auth is explicitly enabled.
- Gated admin key bypass behind `ALLOW_ADMIN_KEY_AUTH`; normal admin access must be authenticated staff JWT.
- Masked API keys/global keys in admin responses and stopped returning full Meta access token from profile.
- Added MercadoPago webhook signature validation with `MP_WEBHOOK_SECRET`.
- Gated debug endpoints behind `ALLOW_DEBUG_ENDPOINTS`.
- Prevented OTP codes from being printed in production logs and hardened password recovery.
- Added JWT validation for admin and presence WebSockets.
- Added SSRF/size protections to Playwright render and video image downloads.

Verification:

- `py -3 manage.py check` OK.
- `py -3 -m py_compile api/views.py api/tasks.py api/consumers.py admin_panel/consumers.py api/services/gemini_video_service.py api/services/lightweight_video_service.py api/services/render_engine.py` OK.

Commit/push:

- No commit.

Pending/risks:

- Rotate leaked `ADMIN_KEY` and exposed provider API keys.
- Set production env: `MP_WEBHOOK_SECRET`, `ALLOW_ADMIN_KEY_AUTH=False`, `ALLOW_DEBUG_ENDPOINTS=False`, strict CORS origins, private/TLS Redis.
- Encrypt DB-stored API keys/tokens in a follow-up migration.
- Note: repo had staged/unrelated `api/views_admin.py` work from another agent; it was not reverted.

### 2026-05-22 - OpenCode - Implement API key bulk dedupe behavior

Objective:

- Make Admin Dashboard bulk API key upload ignore repeated pasted keys, skip keys already in SQL, and automatically remove duplicate SQL APIKey rows when safe.

Files modified:

- `api/views_admin.py`

Changes made:

- Implemented `admin_apikeys_pool_bulk` instead of returning the v2 stub.
- Added request-level dedupe by service + api_key.
- Added existing-key detection so repeated SQL keys are not recreated.
- Added duplicate cleanup for affected services: keeps one canonical key and deletes duplicate rows that have no assignment/history/usage.
- Protects duplicates with `UserAPIAssignment`, API logs, request counters, errors, or `last_used_at` and reports them as `duplicates_protected`.
- Added the same duplicate guard to individual API key creation.
- Returns counts expected by admin UI: `received`, `created`, `duplicates_in_request`, `duplicates_existing`, `duplicates_deleted`, `duplicates_protected`, `duplicate_groups`, `errores`.

Verification:

- `py -3 -m py_compile api/views_admin.py` OK.
- `py -3 manage.py check` OK.

Commit/push:

- Included in commit `fix(admin): dedupe API key bulk upload`.

Pending/risks:

- Bulk cleanup deletes only duplicate APIKey rows without assignment/history/usage. Duplicates with active assignment or historical usage are protected and reported, not deleted, to avoid breaking existing users or audit logs.
- Existing unrelated backend dirty files were not touched.

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

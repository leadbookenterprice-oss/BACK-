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

### 2026-06-05 - Codex - Reporte solicitado

Objetivo actual:

- Coordinar estado entre Codex/agentes activos para LeadBook, sin modificar codigo de producto.
- Contexto inmediato: el usuario pidio primero implementar generacion secuencial con Cerebras y luego acoto el pedido a un cuadro de limites de Cerebras.

Estado actual:

- No se implementaron cambios de producto en esta sesion.
- Se consulto documentacion oficial de Cerebras y se respondio al usuario con tabla de limites: Free Trial `gpt-oss-120b`/`zai-glm-4.7` = 5 RPM, 30K TPM, 1M TPH, 1M TPD; Developer Pay-as-you-go `gpt-oss-120b` = 1K RPM/1M TPM, `zai-glm-4.7` = 500 RPM/500K TPM.
- Recomendacion vigente para LeadBook: usar `gpt-oss-120b`, generacion secuencial, 1 listado completo por vez por key, presupuesto conservador aproximado de 25K tokens por listado completo.

Archivos tocados/sucios:

- Tuyo en esta sesion: solo este `AI_COLLABORATION_LOG.md` para registrar el reporte.
- Preexistentes en `Backend--main`: `.env.example`, `AI_COLLABORATION_LOG.md`, `admin_panel/urls.py`, `admin_panel/views.py`, `admin_panel/views_cloudinary.py`, `api/ai_services.py`, `api/models.py`, `api/services/almacenamiento.py`, `api/services/pool_service.py`, `api/tests.py`, `api/views.py`, `api/views_admin.py`, `api/migrations/0020_cerebras_api_slots.py`, `api/migrations/0021_cloudinarystoragelog_and_more.py`, `api/services/cerebras_slots.py`.
- Preexistentes en `frontend-new`: `.opencode/skills/leadbook-frontend-designer/SKILL.md`, `AGENTS.md`, `AI_AGENT_README.md`, `AI_COLLABORATION_LOG.md`, `src/pages/ResultadosPage.jsx`, `src/services/api.js`.
- Preexistentes en `dash_admin_leadbook-master`: `AI_COLLABORATION_LOG.md`, `src/components/admin/CloudinaryView.jsx`, `src/pages/admin/ApiPoolPage.jsx`.

Verificaciones realizadas:

- Leidos `..\AI_COLLABORATION_LOG.md`, `Backend--main\AI_COLLABORATION_LOG.md` y `frontend-new\AI_COLLABORATION_LOG.md`.
- Ejecutados `git status --short --branch`, `git diff --stat` y `git log --oneline -8` en `Backend--main`, `frontend-new` y `dash_admin_leadbook-master`.
- Verificada documentacion oficial de Cerebras: Rate Limits, Usage & Monitoring y Pricing.

Bloqueos o decisiones necesarias:

- Confirmar si se quiere pasar de informe/plan a implementacion real de generacion secuencial backend-driven.
- Definir si la orquestacion final debe ir por Celery obligatorio o si se acepta fallback sincrono/thread en entornos sin worker.
- Confirmar limite operativo por key: sugerido 30-40 listados/dia/key con margen, no el teorico.

Riesgos de pisar trabajo ajeno:

- Alto en `Backend--main`, `frontend-new` y admin porque hay cambios sucios preexistentes de otros agentes.
- No revertir ni reformatear archivos tocados por OpenCode/Codex previos.
- Si se implementa la generacion secuencial, coordinar antes de editar `api/views.py`, `api/ai_services.py`, `api/models.py`, `src/pages/ResultadosPage.jsx` y `src/services/api.js`.

Proximos 3 pasos concretos:

1. Si el usuario confirma implementacion, crear modelo/estado de corrida de generacion en backend y migracion sin tocar media pesada en Postgres.
2. Instrumentar `call_cerebras_api()` para persistir headers `x-ratelimit-*`, tokens reales/estimados, modelo y error por request.
3. Cambiar `frontend-new` para iniciar `generar-pack`, hacer polling de progreso y mostrar pasos `PDF -> post -> story -> carrusel -> email`.

Comandos o tareas en progreso:

- No hay comandos ni tareas en progreso desde esta sesion.
- Antes de cerrar implementacion futura faltaria correr checks backend/frontend y actualizar logs sin pisar cambios ajenos.

### 2026-06-03 - OpenCode - Cerebras backend slots for generation

Objective:

- Replace permanent Cerebras user-key assignment with temporary backend slots for content generation, without exposing keys to users or using silent fallbacks.

Files modified:

- `.env.example`
- `admin_panel/views.py`
- `api/ai_services.py`
- `api/migrations/0020_cerebras_api_slots.py`
- `api/models.py`
- `api/services/cerebras_slots.py`
- `api/services/pool_service.py`
- `api/views.py`
- `api/views_admin.py`

Changes made:

- Added Cerebras slot lock fields to `APIKey` and migration `0020_cerebras_api_slots.py`.
- Added `api/services/cerebras_slots.py` to reserve/reuse slots, enforce daily token budget, release expired locks, and record slot usage/errors.
- Changed `call_cerebras_api()` to reserve backend slots for authenticated generation, cap completion tokens by task, track token usage manually, and propagate slot/quota/rate-limit errors.
- Fixed `smart_call()` so Cerebras quota/rate-limit errors are not swallowed as generic failures.
- Stopped automatic plan assignment of permanent Cerebras keys by clearing Cerebras entries from `PLAN_API_COUNTS`.
- Updated admin API endpoints/actions to expose slot metadata and clear slot locks on release/reactivate/reset.
- Removed static PDF fallback when Cerebras/IA is unavailable; PDF now returns a controlled quota/provider error or 502 instead of silently rendering static content.
- Added `CEREBRAS_DAILY_TOKEN_LIMIT` and `CEREBRAS_SLOT_TTL_SECONDS` to `.env.example`.

Verification:

- `py -3 -m py_compile "api\services\cerebras_slots.py" "api\ai_services.py" "api\views.py" "api\views_admin.py" "api\services\pool_service.py" "api\models.py" "admin_panel\views.py" "api\migrations\0020_cerebras_api_slots.py"` OK.
- `py -3 manage.py check` OK.
- `py -3 manage.py makemigrations --check --dry-run` OK.
- `git diff --check` OK.

Commit/push:

- No commit or push in this session.

Pending/risks:

- Production must run migrations before deploy; local untracked Cloudinary migration `api/migrations/0021_cloudinarystoragelog_and_more.py` depends on `0020` and was not edited as part of this task.
- Existing dirty Cloudinary/backend changes were left untouched.
- Load one or more `cerebras` APIKey rows in the pool and keep `ALLOW_GLOBAL_API_FALLBACK=False` in production.
- Recommended smoke tests after deploy: no key returns controlled 503, free slot generates, occupied slots return retry payload, exhausted token budget returns hard quota.
- Agent: OpenCode

### 2026-06-03 - OpenCode - Starter daily listing quota and shared Cerebras pool

Objective:

- Implement the new Starter API model: one Cerebras key can serve up to 57 Starter users, with 30 listing creations per user per day, excluding video.

Files modified:

- `api/plan_utils.py`
- `api/services/pool_service.py`
- `api/ai_services.py`
- `api/views.py`
- `api/views_usage.py`
- `api/views_admin.py`

Changes made:

- Added Starter/free daily listing quota helpers: 30 `property` creations per day, explicitly excluding video.
- Enforced the daily listing quota only on `POST /listados/`; video remains separate and does not consume this quota.
- Added quota payloads to listing creation responses, dashboard payloads, `/cuota-ia/`, and `/auth/mi-uso/`.
- Changed Cerebras assignment for Starter/free to shared mode: existing assigned Cerebras keys may receive additional users up to 57 active assignments.
- Kept Pro/Scale/Business behavior unchanged because their new calculations are not defined yet.
- Updated Cerebras default key daily request capacity to `1710` (57 users x 30 listings) for newly created/ensured services.
- Fixed Cerebras calls to prefer the user's assigned key instead of taking the first global pool key.
- Added admin API metadata for Cerebras shared capacity: assigned user count, capacity, available slots, sharing mode, and sample assigned users.

Verification:

- `python -m py_compile api/ai_services.py api/services/pool_service.py api/views.py api/views_usage.py api/views_admin.py api/plan_utils.py` OK.

Commit/push:

- Pending commit in this session.

Pending/risks:

- Existing Cerebras `Servicio` rows will be updated to default limit 1710 when `ensure_core_services()` runs; existing `APIKey.google_daily_limit` values are not migrated automatically.
- Pro/Scale/Business new limits remain intentionally unchanged pending product calculation.

### 2026-06-03 - OpenCode - Make content bundle Cerebras-only

Objective:

- Change the user content-generation bundle to Cerebras only and keep video/voice/social/provider APIs separate from content creation.

Files modified:

- `api/services/pool_service.py`
- `api/tasks.py`
- `api/tracking.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added `CONTENT_BUNDLE_SERVICES = ('cerebras',)`.
- Changed `SERVICIOS_CRITICOS`, plan auto-assignment counts, bundle stats, and compatibility counts so automatic bundle assignment/repair only targets Cerebras.
- Changed free/content pool reset and soft-unavailable handling to use only `CONTENT_BUNDLE_SERVICES`.
- Left Gemini, ElevenLabs, UploadPost, Groq, and the other providers as loadable/assignable services outside the content bundle.

Verification:

- `py -3 -m py_compile "api\services\pool_service.py" "api\tracking.py" "api\tasks.py"` OK.
- `py -3 manage.py check` OK.
- `py -3 manage.py makemigrations --check --dry-run` OK.
- `git diff --check` OK.

Commit/push:

- Local commit will be created after this log update; remote push still depends on GitHub credentials being available.

Pending/risks:

- Existing users may still have older Gemini/ElevenLabs/UploadPost assignments; this change stops automatic bundle repair/assignment for them but does not delete existing assignments.
- Video/voice/social flows still need their own assignment/entitlement rules if they should be automated separately.
- Agent: OpenCode

### 2026-06-03 - OpenCode - Add AI provider service catalog

Objective:

- Add the requested external AI providers to the backend service catalog and SQL seed path so admins can load user-pool keys for them.

Files modified:

- `admin_panel/views.py`
- `api/migrations/0018_ai_provider_services.py`
- `api/services/pool_service.py`
- `api/tasks.py`
- `api/tracking.py`
- `api/views_admin.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added catalog defaults for Gemini AI Studio, Groq, Cerebras, OpenRouter, NVIDIA NIM, Hugging Face, Mistral AI, Cohere, SambaNova, DeepSeek, Cloudflare Workers AI, GitHub Models, plus existing UploadPost/ElevenLabs/Cloudinary.
- Added migration `0018_ai_provider_services` to upsert the service rows in SQL.
- Reused shared `SERVICE_DEFAULTS` in admin key-creation defaults so new services get consistent limits/descriptions.
- Expanded AI pool reset/unavailable handling to use the shared AI service list.
- Left automatic plan assignment unchanged for the existing bundle/core AI services to avoid flooding users/admins with missing-key alerts before stock is loaded.

Verification:

- `py -3 -m py_compile "api\services\pool_service.py" "api\tracking.py" "api\tasks.py" "api\views_admin.py" "admin_panel\views.py" "api\migrations\0018_ai_provider_services.py"` OK.
- `py -3 manage.py check` OK.
- `py -3 manage.py makemigrations --check --dry-run` OK before making `0018` independent; after changing `0018` to depend on tracked `0016`, the dirty local workspace reports a leaf conflict only because unrelated untracked `0017_apikey_cloudinary_health.py` is still present.
- `git diff --check` OK.

Commit/push:

- Local commit created: `f4a56f5 feat(api): seed ai provider services`.
- Remote push to `origin/main` was attempted but failed because GitHub rejected the HTTPS credentials (`Invalid username or token`); `gh` is not installed in this environment.

Pending/risks:

- `api/migrations/0018_ai_provider_services.py` depends on latest tracked migration `0016` so the provider catalog can be pushed without unrelated local Cloudinary schema work.
- Local untracked Cloudinary migration `api/migrations/0017_apikey_cloudinary_health.py` still exists and was not staged.
- Actual generation routing for OpenRouter/NVIDIA/Hugging Face/Mistral/Cohere/SambaNova/DeepSeek/Cloudflare/GitHub Models was not added in this pass; keys can be loaded and assigned via the pool.
- Pre-existing unrelated Cloudinary/backend dirty changes were left untouched.
- Agent: OpenCode

### 2026-06-02 - OpenCode - Switch active generation flow to Cerebras only

Objective:

- Use Cerebras alone for current AI content generation tests and remove Gemini/Groq from the active generation path.

Files modified:

- `api/ai_services.py`
- `api/views.py`

Changes made:

- Simplified `smart_call()` to call Cerebras only.
- Reduced the active HTML generation cascades to Cerebras-only model attempts.
- Left the legacy Gemini/Groq helpers in place but removed them from the live generation path.

Verification:

- `python -m py_compile "api\\ai_services.py" "api\\models.py" "api\\services\\pool_service.py" "api\\views.py" "api\\views_admin.py"` OK.

Commit/push:

- No commit/push.

Pending/risks:

- Legacy provider helpers still exist for future reactivation, but they are no longer used by the current generation flow.
- Agent: OpenCode

### 2026-06-02 - OpenCode - Add Cerebras to AI generation and admin pool

Objective:

- Integrate Cerebras as a first-class AI provider for current content generation and expose it in the admin pool UI.

Files modified:

- `api/ai_services.py`
- `api/models.py`
- `api/services/pool_service.py`
- `api/views.py`
- `api/views_admin.py`

Changes made:

- Added Cerebras chat completion support using the OpenAI-compatible `https://api.cerebras.ai/v1/chat/completions` endpoint with model fallback between `gpt-oss-120b` and `zai-glm-4.7`.
- Updated the generic smart text cascade and the HTML generation cascades so Cerebras is tried before the existing providers.
- Routed `generar_listado`, `generar_escena`, and the shared smart text path through the new cascade instead of calling only Gemini/Groq directly.
- Added Cerebras to the service catalog, per-plan API assignments, and user quota limits so the pool can assign it like the existing AI services.
- Updated the admin API-key creation endpoints so new services can be created with sensible defaults and Cerebras can be loaded from the admin pool.

Verification:

- `python -m py_compile "api\\ai_services.py" "api\\models.py" "api\\services\\pool_service.py" "api\\views.py" "api\\views_admin.py"` OK.

Commit/push:

- No commit/push.

Pending/risks:

- Cerebras quota behavior is inferred from response codes; if the provider changes its error payloads, the exhaustion detection may need tuning.
- The admin global-keys tab remains a stub in the current backend and was not needed for the Cerebras pool flow.
- Agent: OpenCode

### 2026-06-02 - OpenCode - PDF/template/caption/landing stabilization

Objective:

- Fix PDF upload failures, make template choices render different layouts, rotate caption styles, and reduce landing clipping/cut cards.

Files modified:

- `api/services/almacenamiento.py`
- `api/ai_services.py`
- `api/views.py`
- `front-Saas/src/pages/LandingPage.jsx`
- `front-Saas/src/components/landing/HeroSection.jsx`
- `front-Saas/src/components/landing/HowItWorksSection.jsx`
- `front-Saas/src/components/landing/FeaturesSection.jsx`
- `front-Saas/src/components/ui/pricing-section-4.jsx`
- `front-Saas/src/components/ui/CardSwap.css`

Changes made:

- **PDF upload**: Cloudinary upload now wraps raw PDF bytes in `BytesIO` before sending them to the SDK, which removes the fragile raw-bytes path.
- **Template selection**: The custom template aliases now resolve to different physical HTML templates instead of collapsing to the same mediterraneo layout.
- **Captions**: Added three caption style archetypes (`storytelling`, `commercial`, `investment`) with rotation/persistence per listing and per format, so successive generations do not reuse the same tone.
- **Landing layout**: Expanded hero width slightly, reduced oversized title sizing, increased `GooeyText` height, reduced some card paddings/heights, and made the landing card content scrollable with extra bottom room.

Verification:

- `python -m py_compile "back-\\Back-\\api\\views.py" "back-\\Back-\\api\\ai_services.py" "back-\\Back-\\api\\services\\almacenamiento.py"` OK.
- `npm run build` in `front-Saas` OK.

Commit/push:

- No commit/push.

Pending/risks:

- PDF generation still depends on valid Cloudinary credentials/network in the production environment.
- Very short viewports may still need one more spacing pass if the remaining landing sections are visually dense.
- Agent: OpenCode

### 2026-06-02 - OpenCode - Remove real admin bootstrap and API assignments

Objective:

- Ensure the admin dashboard uses only env-backed credentials/session tokens and never creates or depends on a real `Agent` user that occupies API keys.

Files modified:

- `railway.json`
- `api/management/commands/ensure_staff_admin.py`
- `api/management/commands/cleanup_bootstrap_admin.py`
- `api/management/commands/fix_missing_apis.py`
- `api/models.py`
- `api/services/pool_service.py`
- `api/views_admin.py`
- `admin_panel/tests.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Removed `ensure_staff_admin` from the Railway web startup path.
- Added `cleanup_bootstrap_admin` to Railway startup so the legacy real admin `Agent` is soft-deleted and any active API assignments are released back to the pool.
- Made `ensure_staff_admin` opt-in only via `ALLOW_STAFF_ADMIN_BOOTSTRAP=True` and removed its hardcoded default password/email behavior.
- Blocked staff/superuser accounts from receiving base or extra API assignments in `APIPoolService`.
- Updated `Agent` post-save signals to skip staff/superuser API assignment and release any existing staff assignments on save.
- Excluded staff/superusers from admin user listing, admin auto-repair, and `fix_missing_apis`.
- Added regression tests for staff not receiving APIs, normal users still receiving APIs, and cleanup releasing/deleting the legacy admin user.

Verification:

- `py -3 -m py_compile admin_panel/tests.py api/management/commands/ensure_staff_admin.py api/management/commands/cleanup_bootstrap_admin.py api/management/commands/fix_missing_apis.py api/models.py api/services/pool_service.py api/views_admin.py` OK.
- `py -3 manage.py test admin_panel.tests.AdminSessionAuthTests admin_panel.tests.AdminBootstrapCleanupTests` OK, 5 tests.
- `py -3 manage.py check` OK.
- `py -3 -c "import json; json.load(open('railway.json', encoding='utf-8')); print('railway.json OK')"` OK.
- `git diff --check` OK.
- Grep confirmed no `LeadBookAdmin2026` hardcoded password remains and Railway startup calls `cleanup_bootstrap_admin`, not `ensure_staff_admin`.

Commit/push:

- Committed and pushed to `origin/main`: `00e2fe8 fix(admin): remove real admin bootstrap`.

Pending/risks:

- Deploy backend so Railway runs `cleanup_bootstrap_admin` once at startup; after that `LeadBook Admin #10` should disappear from normal users and its assigned keys should return to available unless another active assignment uses them.
- Production still needs `ADMIN_DASH_EMAIL` and `ADMIN_DASH_PASSWORD` or `ADMIN_DASH_PASSWORD_SHA256` for dashboard login.

### 2026-05-25 - OpenCode - Admin dashboard env-backed session login

Objective:

- Let the admin dashboard authenticate without depending on a real `Agent` user, while avoiding hardcoded frontend secrets or API-consuming ghost users.

Files modified:

- `.env.example`
- `admin_panel/auth.py`
- `admin_panel/consumers.py`
- `admin_panel/tests.py`
- `admin_panel/views.py`
- `admin_panel/views_cloudinary.py`
- `api/admin.py`
- `api/urls.py`
- `api/views.py`
- `api/views_admin.py`
- `subzero_core/settings.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added `/api/auth/admin-login/` and `/api/auth/admin-profile/` backed by `ADMIN_DASH_EMAIL` and `ADMIN_DASH_PASSWORD`/`ADMIN_DASH_PASSWORD_SHA256` env vars.
- Added signed, time-limited admin session tokens using Django signing; no `Agent` is created, looked up, or assigned API pool resources for this admin login.
- Added shared `is_admin_request()` auth helper for admin endpoints, preserving staff JWT and gated `X-Admin-Key` compatibility.
- Updated admin HTTP endpoints and admin WebSocket auth to accept the new admin session token.
- Added `X-Admin-Session` to CORS allowed headers.
- Documented new env vars in `.env.example`: `ADMIN_DASH_EMAIL`, `ADMIN_DASH_PASSWORD`, `ADMIN_SESSION_TTL_HOURS`.
- Added regression tests proving admin session login does not require/create a real user and can access `/api/admin/stats/`.

Verification:

- `py -3 -m py_compile admin_panel/auth.py admin_panel/consumers.py admin_panel/views.py admin_panel/views_cloudinary.py admin_panel/tests.py api/urls.py api/views.py api/views_admin.py api/admin.py subzero_core/settings.py` OK.
- `py -3 manage.py test admin_panel.tests.AdminSessionAuthTests` OK, 2 tests.
- `py -3 manage.py check` OK.
- `git diff --check` OK.

Commit/push:

- Committed and pushed to `origin/main`: `297a5ef feat(admin): add env-backed admin sessions`.

Pending/risks:

- Production backend must set `ADMIN_DASH_EMAIL` and `ADMIN_DASH_PASSWORD` or `ADMIN_DASH_PASSWORD_SHA256` before the admin dashboard can log in with the new flow.
- Keep `ALLOW_ADMIN_KEY_AUTH=False` in production unless an emergency internal bypass is explicitly needed.
- Existing unrelated backend dirty changes for Gemini/pool/Railway remain in the original local `Backend--main` worktree and were not included in this push.

### 2026-05-29 - Antigravity - Fix double gallery in marketing emails

Objective:

- Fix double photo galleries appearing in generated marketing emails.

Files modified:

- `api/views.py`

Changes made:

- **generar_email**: Commented out the manual HTML gallery block injection via regex replacement at the end of email rendering. Since all premium templates natively loop over `galeria_urls` in Django's template language, this manual injection was causing duplicate gallery rows.

Verification:

- Compiled `api/views.py` successfully (`python -m py_compile` with zero syntax errors).
- Double-checked email template structures (`marketing.html`, `marketing_manhattan.html`) to ensure native Django template tags loop over `galeria_urls` perfectly.

Commit/push:

- Committed and pushed backend changes successfully (`01663ae`).

Pending/risks:

- None.

### 2026-05-28 - Antigravity - Fix onboarding 400 errors, DB migrations, pricing fix & Plan seeding

Objective:

- Fix HTTP 400 errors during onboarding when frontend POST to `/api/auth/agentes-comerciales/` fails repeatedly with "Error al crear agente comercial".
- Run backend database migrations locally to ensure schema health.
- Correct ARS prices and limits in database seed files, then populate the Plan table with Starter, Pro, Scale, and Business plans.
- Update plan checking scripts to list database plans gracefully.
- Fix PDF template mapping resolution bug in `generar_html_desde_template` where custom Mediterranean template aliases were not normalized and mapped to their physical HTML layouts, causing fallback rendering that looked exactly the same regardless of selection.

Files modified:

- `api/views.py`
- `api/ai_services.py`
- `create_plans.py`
- `check_plans.py`

Changes made:

- **OnboardingView**: Auto-creates a default `ComercialAgentProfile` from user data (nombre, email, telefono, logo_url) if none exists after saving user fields. Handles `IntegrityError` gracefully for race conditions.
- **commercial_agents_collection POST**: Added flexible field name mapping (name→nombre, phone→telefono_e164, etc.) so frontend variants are accepted. Default `nombre` to user's name when missing. Wrapped creation in `transaction.atomic()`. Added `IntegrityError` handling for the `unique_default_commercial_agent_per_owner` constraint — retries creation without `is_default` if constraint is violated.
- **create_plans.py**: Fully rewritten to seed the database plans (Starter, Pro, Scale, Business) according to the current model structure (precios ARS and daily API limits).
- **check_plans.py**: Updated to output the plans and pricing currently in the database without raising an exception if a specific test agent is missing.
- **api/ai_services.py**: Registered all 10 templates (including the 5 new Mediterranean custom color system variants: `costa_serena`, `oliva_natural`, `terracota_suave`, `brisa_calida`, `arena_clara`) under `TEMPLATE_IDS` and mapped them to their color configurations and the physical base template `template_mediterraneo.html` inside `_template_file_from_id`. Updated `_resolve_theme_from_context` to handle both file name matches and normalized template ID matches correctly, unlocking all visual style variations.

Verification:

- `python -m py_compile api/views.py` OK.
- `python manage.py migrate` OK (Ran migrations api.0003 through api.0016 successfully).
- `python create_plans.py` OK (Plans populated successfully).
- `python check_plans.py` OK (Lists Starter, Pro, Scale, Business plans with correct ARS prices and limits).

Commit/push:

- Committed and pushed backend changes.

Pending/risks:

- Deploy migrations and seed the updated plans in the production database (Postgres).

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

### 2026-05-24 - OpenCode - Gemini pool exhaustion and Railway worker detection

Objective:

- Prevent Gemini/ElevenLabs pool selection from reusing exhausted API keys and make Railway start Celery when the deployed service is clearly a worker.

Files modified:

- `api/ai_services.py`
- `api/pool_manager.py`
- `api/services/pool_service.py`
- `api/tracking.py`
- `api/tests.py`
- `railway.json`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added `exclude_keys` support to `get_next_available_api` and excluded keys with `exhausted`, `dead`, or `disabled` status from active selection.
- Updated Gemini retry/rotation to track soft-limited keys and try another available pool key before waiting on the same key.
- Made pool repair skip exhausted keys and made usage tracking reject exhausted/dead/disabled assignments.
- Marked assignments that reach daily/monthly limits as exhausted instead of leaving them selectable.
- Added regression tests for not reusing exhausted keys and repairing exhausted assignments with an available key.
- Updated `railway.json` so worker mode is selected either by `APP_ROLE=worker` or by Railway service identifiers/names containing `worker`, `celery`, `queue`, or `video`.

Verification:

- `py -3 -m py_compile api/tests.py api/ai_services.py api/pool_manager.py api/services/pool_service.py api/tracking.py` OK.
- `py -3 manage.py test api.tests.GeminiPoolSelectionTests api.tests.ListingResultPersistenceTests api.tests.AdsStudioEndpointTests` OK, 13 tests.
- `py -3 manage.py check` OK.
- `py -3 -c "import json; json.load(open('railway.json', encoding='utf-8')); print('railway.json OK')"` OK.
- `git diff --check` OK.

Commit/push:

- Not committed or pushed.

Pending/risks:

- Production still needs a real Railway worker service with `APP_ROLE=worker` or a worker/celery/queue/video service name, plus `REDIS_URL`, `CELERY_TASK_ALWAYS_EAGER=False`, and `VIDEO_GENERATION_MODE=celery`.
- Production env should avoid conflicting `GOOGLE_API_KEY`/`GEMINI_API_KEY` values if the SDK prioritizes `GOOGLE_API_KEY`.

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

### 2026-05-24 - OpenCode - PDF proxy/download consistency

Objective:

- Fix result pages showing a PDF preview/download state when the backend has no persisted PDF file URL, causing `pdf-proxy`/download 404s like "No hay PDF generado todavia".

Files modified:

- `api/views.py`
- `api/tests.py`
- `AI_COLLABORATION_LOG.md`

Changes made:

- Added `pdf-proxy` fallback to render a legacy saved HTML PDF into an inline PDF when no Cloudinary URL exists.
- Kept the existing direction that new `/generar-pdf/` responses should only succeed after a real PDF is rendered/uploaded and URL persisted.
- Added test coverage for `pdf_proxy` rendering from saved HTML when URL is absent.
- Preserved existing local quota-notification changes in `api/views.py`/`api/tests.py`; did not revert or rewrite them.

Verification:

- `py -3 -m py_compile api/views.py api/tests.py` OK.
- `py -3 manage.py test api.tests.ListingResultPersistenceTests api.tests.AdsStudioEndpointTests` OK, 11 tests.
- `py -3 manage.py check` OK.
- `git diff --check` OK.

Commit/push:

- Not committed or pushed.

Pending/risks:

- Production should be deployed with the paired frontend fix so HTML-only previews no longer show a false "Descargar PDF" action.
- Listings with only HTML and no Cloudinary PDF URL remain legacy fallback only; preferred state is a persisted Cloudinary PDF URL.

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

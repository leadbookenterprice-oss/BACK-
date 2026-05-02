# Informe Backend LeadBook — 2026-04-18

Este documento resume el análisis completo del backend, los **fixes aplicados** y los **problemas pendientes** que dependen de config externa (no se pueden arreglar desde código).

---

## 1. Tests end-to-end (resultado actual)

Ejecutados con `scratch/test_flow_e2e.py`:

| Paso | Endpoint | Resultado |
|---|---|---|
| 1 | `POST /api/v1/auth/send-otp/` | ✅ 200 |
| 2 | `POST /api/v1/auth/verify-otp/` | ✅ 200 |
| 3 | `POST /api/v1/auth/register/` | ✅ 201 + JWT |
| 4 | `POST /api/v1/auth/login/` | ✅ 200 |
| 5 | `POST /api/v1/generar-guion/` | ✅ 200 (4 escenas) |
| 6 | `POST /api/v1/generar-listado/` | ✅ 200 (copy real de Groq) |

---

## 2. Fixes aplicados

### 2.1 `.env` (reescrito)
- Se cargaron las keys reales: `GEMINI_API_KEY`, `GROQ_API_KEY`, `ELEVENLABS_API_KEY`, `UPLOADPOST_API_KEY`.
- `DEBUG=True` para dev local.
- `ALLOWED_HOSTS` incluye `localhost`, `127.0.0.1`, `testserver`.
- `CORS_ALLOWED_ORIGINS` incluye los orígenes del frontend dev (Vite 5173, CRA 3000).
- `GMAIL_USER=fieldultramedia@gmail.com` pre-cargado. **Falta `GMAIL_APP_PASSWORD`** (16 caracteres generados en https://myaccount.google.com/apppasswords).

### 2.2 `subzero_core/settings.py`
- Agregadas constantes `ELEVENLABS_API_KEY` y `UPLOADPOST_API_KEY` (antes no existían — por eso `pool_manager.py` siempre devolvía string vacío).
- Backend de email con **fallback a consola** cuando no hay `GMAIL_APP_PASSWORD`. Así el OTP se loguea por stdout para seguir testeando sin bloquear el flujo.
- `DEFAULT_FROM_EMAIL` pasa a ser `LeadBook <fieldultramedia@gmail.com>` cuando hay SMTP válido.
- `SQLITE_PATH` configurable (permite override del path del SQLite para filesystems donde no funciona bien el locking).
- `conn_max_age=600` mantenido, `OPTIONS={'timeout': 20}` agregado al SQLite.

### 2.3 `api/tasks.py` (OTP email)
Reescrito `send_otp_email_async`:
- HTML + texto plano (EmailMultiAlternatives).
- Connection explícita con timeout de 20s para no colgar workers.
- Fallback a consola si falta `GMAIL_APP_PASSWORD`.
- `traceback.print_exc()` en caso de error SMTP (antes comía los errores).

### 2.4 `api/ai_services.py`
- `call_groq_api`:
  - Modelo default actualizado: `llama-3.1-8b-instant` (el `llama3-8b-8192` fue **decomisionado por Groq**).
  - Fallback automático a `llama-3.3-70b-versatile` si el primario falla por deprecación.
  - Chequeo de key vacía con error claro.
- Nada cambiado en `call_gemini_api` ni `call_elevenlabs_api` (ya estaban OK).

### 2.5 `api/views.py`
- `generar_listado`: si Groq falla, intenta Gemini como fallback. Si ambos fallan, responde 503 con detalle (antes tiraba 500 sin mensaje).

### 2.6 `api/services/instagram_service.py`
- `publicar_post_upload_api`: ahora lee `UPLOADPOST_API_KEY` (convención del proyecto) en lugar del antiguo `UPLOAD_POST_API_KEY` huérfano.
- Endpoint actualizado a `https://api.upload-post.com/api/uploadposts/posts` con auth `Apikey` (coherente con el resto del código).

---

## 3. Problemas detectados — **NO son bugs de código**

### 3.1 ⚠️ Gemini API — cuota en 0
Respuesta de Google al probar la key directamente:

```
429 RESOURCE_EXHAUSTED
Quota exceeded for metric: generate_content_free_tier_input_token_count, limit: 0
```

La key es válida, pero el proyecto Google asociado tiene **cuota 0 en el tier gratuito**. Hay que:
- Entrar a https://aistudio.google.com/ con la cuenta dueña de esa key.
- Ir a "API Keys" → proyecto → habilitar billing o cambiar a otra API key con cuota disponible.
- O generar una key nueva desde otro proyecto con free tier activo.

El fallback a Groq funciona en `generar-listado`, pero `generar-guion` e imágenes dependen de Gemini para los mejores resultados.

### 3.2 ⚠️ ElevenLabs API — key sin permisos
Respuesta al probar `/v1/voices`:

```
401 missing_permissions — falta permiso voices_read
```

La key no tiene los permisos mínimos para TTS. Hay que:
- Entrar a https://elevenlabs.io/ → Profile → API Keys.
- Editar la key o crear una nueva **con permisos de Text-to-Speech habilitados**:
  - `voices_read`
  - `text_to_speech`

### 3.3 ✅ Upload Post — OK
```
200 OK — {"success": true, "profiles": [], "limit": 2, "plan": "default"}
```

La key funciona. Los endpoints `/conexiones/init/` y `/conexiones/estado/` deberían andar.

### 3.4 ✅ Groq — OK
Responde normalmente. Las generaciones de texto están operativas.

### 3.5 📧 Gmail SMTP — falta APP PASSWORD
El correo sigue sin salir hasta que me pases `GMAIL_APP_PASSWORD`. Mientras tanto el OTP se **loguea en la consola del servidor** (backend cae a `console.EmailBackend` automático). Flujo de registro **sí funciona end-to-end** viendo el código por terminal.

Para generar el APP PASSWORD:
1. Cuenta `fieldultramedia@gmail.com` → activar 2FA: https://myaccount.google.com/security
2. https://myaccount.google.com/apppasswords → crear "LeadBook Backend".
3. Copiar los 16 caracteres (sin espacios).
4. Pegarlos en `.env`: `GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx`
5. Reiniciar el servidor Django.

### 3.6 🔐 Exposición de secretos — rotar ya
Las 4 API keys (Gemini, Groq, ElevenLabs, Upload Post) y las del `cargar_pool.py` fueron compartidas en texto plano. **Recomiendo rotarlas** aunque las hayas cargado en `.env`, por principio de seguridad.

---

## 4. Notas adicionales sobre el código

- `api/models.py` `Suscripcion.agente` es `OneToOneField` pero `views.py` a veces asume que puede no existir. Revisar si se crea Suscripcion al registrar (actualmente **no** se crea en `RegisterView`).
- `api/views.py` importa `incrementar_uso` pero en `plan_utils.py` el método es un `pass`. El contador de uso no se incrementa. Hay otra función `registrar_uso` que sí escribe en `UsageLog`. El `puede_generar` lee de `UsageLog`, así que hoy los límites no se aplican.
- `api/services/video_service.py` usa `call_elevenlabs_api` — cuando la key quede con permisos, testear el generador de video.
- Hay `resend==2.27.0` y `stripe==15.0.1` en requirements pero **no se usan**. Podés sacarlos para reducir surface.

---

## 5. Cómo correr y testear

```bash
# 1. Cargar el venv e instalar deps
pip install -r requirements.txt

# 2. Migrar (con SQLITE_PATH opcional si BASE_DIR no soporta locking)
python manage.py migrate

# 3. Test E2E (no requiere servidor corriendo)
python scratch/test_flow_e2e.py

# 4. Test de APIs externas
python scratch/test_apis_directo.py

# 5. Cargar el pool de cuentas (para usuarios free)
python manage.py cargar_pool

# 6. Levantar el server
python manage.py runserver 0.0.0.0:8000
```

---

## 6. Checklist rápido para producción

- [ ] Pasar `GMAIL_APP_PASSWORD` real al `.env` (o cambiar a Resend).
- [ ] Rotar las 4 API keys expuestas.
- [ ] Actualizar cuota de Gemini (billing + upgrade) o rotar a key con cuota.
- [ ] Habilitar permisos TTS en la key de ElevenLabs.
- [ ] Cambiar `SECRET_KEY` de Django por uno fuerte en prod.
- [ ] `DEBUG=False` en prod, `ALLOWED_HOSTS` solo el dominio real.
- [ ] `DATABASE_URL` real (PostgreSQL) en prod.
- [ ] Configurar Redis (`REDIS_URL`) para que Celery mande los OTP asíncronos y no bloquee requests.
- [ ] Configurar Cloudinary (`CLOUDINARY_*`) para que la subida de imágenes funcione.
- [ ] Configurar MercadoPago (`MP_*`) para cobros.
- [ ] Implementar `incrementar_uso` en `plan_utils.py` o consolidar con `registrar_uso`.

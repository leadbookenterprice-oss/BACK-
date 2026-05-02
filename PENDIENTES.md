# LEADBOOK — PENDIENTES Y ESTADO (13 Abril 2026)

## BUGS RESUELTOS HOY ✅

| # | Bug | Causa | Fix aplicado |
|---|-----|-------|--------------|
| 1 | 500 en /generar-imagen-post/, /generar-imagen-story/, /generar-carrusel/ | `generate_social_image` no importado en views.py | `from .image_generator import generate_social_image` agregado |
| 2 | Dashboard KPIs en 0 / spinner | `/api/dashboard/` devolvía campos con nombres distintos | Reescrito dashboard() con campos que espera el front |
| 3 | get_plan_info_mp daba NameError | Llamaba a `get_suscripcion` que fue eliminado | Reescrito con LIMITES dict de plan_utils |
| 4 | MP webhook actualizaba campo legacy `plan` | `agent.plan = plan` en lugar de `agent.plan_nombre` | Cambiado a `agent.plan_nombre = plan` |
| 5 | Admin Usuarios mostraba 0 usuarios | `data` es `{usuarios:[...]}`, el front trataba como array | Fix: `data.usuarios \|\| []` |
| 6 | Admin Usuarios mostraba fecha vacía | Usaba `u.date_joined` (no existe) | Cambiado a `u.fecha_registro` |
| 7 | cloudinary no importado a nivel módulo | Import local dentro de función | `import cloudinary; import cloudinary.uploader` agregados al top |
| 8 | ADMIN_KEY vacío | No estaba en .env | Agregado `ADMIN_KEY=leadbook_admin_2025` al .env |

---

## BUGS PENDIENTES (Prioridad Alta)

### BUG A — Voiceover ElevenLabs no testeado end-to-end
**Archivo:** `api/services/video_service.py`
**Para probar:** Crear listado → activar toggle voiceover → generar video → ver si el video tiene audio.

### BUG B — UploadPost conexiones no probado end-to-end
**Archivos:** `api/views.py` (conexiones_init, conexiones_estado)
**Para probar:** Front → Cuenta → Conexiones → "Conectar mis redes" → ver si abre URL de OAuth de UploadPost.

### BUG C — Email (generar-email) puede fallar si Gemini devuelve markdown en JSON
**Archivo:** `api/views.py` (generar_email)
**Estado:** Hay un fallback, pero si Gemini devuelve markdown malformado el JSON parse falla silenciosamente.
**Fix sugerido:** Mejorar el regex de cleanup o usar `json.loads` con un strip más agresivo.

### BUG D — Video generation con Remotion no testeado localmente
**Archivo:** `api/services/video_service.py`, `video_engine/`
**Requiere:** Node.js + Remotion instalado en el entorno.

---

## MEJORAS PENDIENTES (Prioridad Media)

### MEJORA 1 — Página de resultados incompleta
**Archivo:** `frontend/src/pages/ResultadosPage.jsx` y `components/results/`
**Estado:** Tabs implementados (TabPDF, TabPost, TabStory, TabCarrusel, TabEmail, TabVideo)
**Falta verificar:** Que todos los previews muestren correctamente y los botones de descarga y publicación funcionen.

### MEJORA 2 — Carrusel sin drag-and-drop para reordenar slides
**Archivo:** `frontend/src/components/results/TabCarrusel.jsx`
**Fix:** Implementar react-beautiful-dnd o similar para permitir reordenar slides antes de publicar.

### MEJORA 3 — Pantalla "límite alcanzado" con botón upgrade
**Estado:** El backend devuelve `{error: "limite_alcanzado", upgrade_url: "/precios"}` pero el front no siempre muestra un modal/pantalla atractiva.

### MEJORA 4 — Dominio propio en Resend
**Estado:** Solo llega a ooaipi4@gmail.com hasta tener dominio verificado.
**Acción:** Verificar dominio en Resend y cambiar FROM en send_otp_email_async.

### MEJORA 5 — Cloudinary estrategia por usuario
**Estado:** Todos los assets se suben a carpetas compartidas (leadbook/posts, leadbook/stories, etc.)
**Pendiente:** Definir si se usa pool de cuentas Cloudinary también o una cuenta empresa.

---

## BACKLOG (Prioridad Baja / Fase 2)

- [ ] Suscripciones automáticas con MercadoPago (actualmente pago único)
- [ ] App móvil con Capacitor
- [ ] Publicación automática al generar (actualmente es manual vía UploadPost)
- [ ] Multi-nicho (e-commerce, servicios, restaurantes, etc.)
- [ ] Historial con descarga de assets anteriores
- [ ] Dashboard con gráficos de uso por tiempo

---

## INSTRUCCIONES PARA PUSH A RAILWAY

### Back (después de cualquier cambio en Python):
```bash
cd "C:\Users\elalc\Desktop\new leadbook\Back--master"
git add api/views.py
git commit -m "Fix: imports generate_social_image y cloudinary, dashboard fields, get_plan_info_mp, webhook plan"
git push origin master -f
# Luego hacer Redeploy en Railway del servicio Back- y del worker lucid-curiosity
```

### Front (después de cambios en React):
```bash
cd "C:\Users\elalc\Desktop\new leadbook\front-Saas-master"
git add frontend/src
git commit -m "descripcion"
git push origin master -f
# Redeploy front-Saas en Railway (Root dir: frontend/)
```

### Admin (solo corre local):
```bash
cd "C:\Users\elalc\Desktop\LEADBOOK UP\admin-dashboard"
git add src/pages/UsuariosPage.jsx
git commit -m "Fix: leer data.usuarios del response, usar fecha_registro"
git push https://github.com/fieldultramedia-ai/DASH.git master -f
npm run dev  # → localhost:5173
```

### Variables Railway que deben estar seteadas:
- Todas las del .env de este repo
- ADMIN_KEY=leadbook_admin_2025 (NUEVA — agregar si no está)

---

## NOTAS CRÍTICAS PARA NO REPETIR ERRORES

1. `plan_nombre` — NUNCA usar `plan` (campo legacy)
2. `fecha_registro` — NUNCA usar `date_joined` (no existe en Agent)
3. `agente` — NUNCA usar `agent` en FK de Listado
4. `subzero_access` — token en localStorage, NUNCA 'token'
5. `get_suscripcion` — fue eliminado, NUNCA importarlo
6. Plan model — NUNCA crear objetos Plan, está roto. Usar LIMITES dict de plan_utils.py
7. Railway usa branch `master`, no `main`

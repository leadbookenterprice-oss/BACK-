# LISTO.md — LeadBook · Estado final + Instrucciones Railway
Fecha: 13/04/2026

---

## QUE QUEDO FUNCIONANDO

### Backend (Back--master)
- [x] Autenticación JWT (login / register / recuperar contraseña)
- [x] Dashboard endpoint → devuelve KPIs correctos con campo names alineados al frontend
- [x] /generar-pdf/ → genera PDF con WeasyPrint y sube a Cloudinary
- [x] /generar-imagen-post/ → genera imagen 1080x1080 (Pillow) y sube a Cloudinary
- [x] /generar-imagen-story/ → genera imagen 1080x1920 (Pillow) y sube a Cloudinary
- [x] /generar-carrusel/ → genera múltiples imágenes y las sube a Cloudinary
- [x] /generar-email/ → genera HTML de email con Gemini
- [x] /generar-guion/ → genera guión cinematográfico con Gemini Flash 2.0
- [x] Admin endpoints con X-Admin-Key header
- [x] MercadoPago checkout + webhook (campo plan_nombre correcto)
- [x] Conexiones UploadPost (init + estado)
- [x] Limites por plan con LIMITES dict (no más get_suscripcion)

### Frontend (front-Saas-master)
- [x] Wizard de 7 pasos completo (NuevoPage + Step01–Step07)
- [x] Step07 con validación de teléfono (7-15 dígitos)
- [x] ResultadosPage con loading overlay y 5 tabs en paralelo
- [x] TabPDF con descarga y vista previa
- [x] TabPost con botón Descargar + botón Publicar en Instagram
- [x] TabStory con botón Descargar + botón Publicar en Instagram
- [x] TabCarrusel con drag-and-drop nativo, descarga por slide y descarga de todos
- [x] TabEmail con vista de HTML
- [x] TabVideo con generación local via Canvas + Ken Burns
- [x] InstagramModal con edición de caption antes de publicar
- [x] DashboardPage con KPIs animados, plan bar, listados recientes, borradores
- [x] TabConexiones con flujo UploadPost OAuth, recarga manual y manejo de errores
- [x] API_BASE_URL desde VITE_API_BASE_URL (no más URLs hardcodeadas)

### Admin Dashboard (LEADBOOK UP/admin-dashboard)
- [x] UsuariosPage lee data.usuarios (no data directo)
- [x] Columna de fecha usa fecha_registro (no date_joined)

---

## ARCHIVOS MODIFICADOS (por repo)

### Back--master
```
api/views.py              # 4 fixes: import cloudinary, import generate_social_image,
                          #          reescritura dashboard(), fix get_plan_info_mp(),
                          #          fix webhook plan_nombre
.env                      # CREADO: todas las env vars + ADMIN_KEY=leadbook_admin_2025
PENDIENTES.md             # CREADO: backlog de bugs y tareas pendientes
LISTO.md                  # CREADO: este archivo
```

### front-Saas-master
```
frontend/src/components/results/TabPost.jsx        # botón descarga imagen
frontend/src/components/results/TabStory.jsx       # botón descarga imagen
frontend/src/components/results/TabCarrusel.jsx    # reescritura: drag-and-drop, descargas
frontend/src/components/cuenta/TabConexiones.jsx   # fix API URL + UX mejorado
```

### LEADBOOK UP/admin-dashboard
```
src/pages/UsuariosPage.jsx    # fix data.usuarios + fecha_registro
```

---

## COMO HACER EL PUSH A RAILWAY

Railway despliega automáticamente cuando hacés push a la rama `master`.
**NO usar rama `main`** — Railway está configurado para `master`.

### PASO 1 — Backend (Back--master)

```bash
cd "C:\Users\elalc\Desktop\new leadbook\Back--master"

# Ver qué cambió
git status
git diff api/views.py

# Agregar solo los archivos modificados (NO el .env — contiene secretos)
git add api/views.py PENDIENTES.md LISTO.md

# Commit
git commit -m "fix: dashboard KPIs, imports cloudinary/generate_social_image, plan_nombre en webhook"

# Push a Railway
git push origin master
```

⚠️ IMPORTANTE: NO hacer `git add .env` — el .env tiene claves privadas.

### PASO 2 — Agregar ADMIN_KEY en Railway (una sola vez)

1. Ir a railway.app → tu proyecto backend → Variables
2. Agregar: `ADMIN_KEY = leadbook_admin_2025`
3. Railway redespliega automáticamente

### PASO 3 — Frontend (front-Saas-master)

```bash
cd "C:\Users\elalc\Desktop\new leadbook\front-Saas-master"

# Ver cambios
git status

# Agregar archivos modificados
git add frontend/src/components/results/TabPost.jsx
git add frontend/src/components/results/TabStory.jsx
git add frontend/src/components/results/TabCarrusel.jsx
git add frontend/src/components/cuenta/TabConexiones.jsx

# Commit
git commit -m "feat: descarga de imágenes en tabs, drag-and-drop carrusel, fix TabConexiones"

# Push a Railway
git push origin master
```

### PASO 4 — Admin Dashboard (LEADBOOK UP/admin-dashboard)

```bash
cd "C:\Users\elalc\Desktop\LEADBOOK UP\admin-dashboard"

# Ver cambios
git status

# Agregar el archivo modificado
git add src/pages/UsuariosPage.jsx

# Commit
git commit -m "fix: admin UsuariosPage lee data.usuarios y muestra fecha_registro"

# Push a Railway (o Vercel/Netlify si está separado)
git push origin master
```

---

## VERIFICACION POST-DEPLOY

Después de que Railway termine de desplegar (1-3 min), verificar:

```
1. GET  /api/dashboard/          → debe devolver { listados_este_mes, total_generados, ... }
2. POST /api/generar-imagen-post/ → debe devolver { url: "https://res.cloudinary.com/..." }
3. POST /api/generar-imagen-story/ → ídem
4. POST /api/generar-carrusel/    → debe devolver { slides: [...] }
5. GET  /api/admin/usuarios/      → con header X-Admin-Key: leadbook_admin_2025
```

---

## PENDIENTES NO CRITICOS (no bloquean el lanzamiento)

Ver PENDIENTES.md para el backlog completo. Los más importantes:

1. **Voiceover ElevenLabs**: no testeado end-to-end en producción
2. **Email Gemini**: puede fallar si Gemini devuelve JSON malformado (agregar parsing robusto)
3. **Video Remotion**: la generación server-side con Remotion no fue testeada localmente
4. **Pantalla límite alcanzado**: el backend devuelve `{error: "limite_alcanzado"}` pero falta modal visual atractivo con botón "Ampliar plan"
5. **Historial completo**: /historial route existe pero sin descarga de assets generados

---

## VARIABLES DE ENTORNO REQUERIDAS EN RAILWAY

Confirmar que estas existan en el panel de Railway del backend:

```
DATABASE_URL          # PostgreSQL de Railway (ya debería estar)
SECRET_KEY            # Django secret key
DEBUG                 # False en producción
ALLOWED_HOSTS         # *.railway.app
CLOUDINARY_URL        # o CLOUDINARY_CLOUD_NAME + KEY + SECRET
GOOGLE_API_KEY        # Gemini Flash 2.0
ELEVENLABS_API_KEY    # para voiceover (si está activo)
UPLOADPOST_API_KEY    # para conexiones sociales
MERCADOPAGO_ACCESS_TOKEN
MP_WEBHOOK_SECRET
REDIS_URL             # para Celery (si las tareas async están activas)
ADMIN_KEY             # leadbook_admin_2025  ← NUEVO, agregar si no está
```

Para el frontend en Railway:
```
VITE_API_BASE_URL     # URL del backend, ej: https://back-production-5895.up.railway.app/api
VITE_CLOUDINARY_CLOUD_NAME
VITE_CLOUDINARY_UPLOAD_PRESET
```

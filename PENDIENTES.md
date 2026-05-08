# Pendientes y Bugs a Resolver

## 🔴 Admin Dashboard — USO HOY siempre muestra 0
- El endpoint `/api/admin/apikeys/pool/` devuelve `requests_today: 0` para keys asignadas via bundle
- El código en `views_admin.py` cruza con `UserAPIQuota` pero el resultado no se refleja
- `UserAPIQuota` tiene los datos correctos (verificado via debug endpoint)
- Los prints `[POOL DEBUG]` en el código nunca aparecen en los logs de Railway
- Pendiente: verificar por qué el código nuevo no ejecuta en producción

## 🔴 Migración pendiente de schema
- El cambio `daily_limit default=1500` en `UserAPIQuota` tiene migración de datos (0036) pero la migración de schema (0037) puede estar en conflicto
- Railway muestra "No migrations to apply" pero el warning de modelos desincronizados apareció antes

## 🟡 Badge BLOQUEADO en admin dashboard
- El campo `is_blocked` no llega en el response del pool endpoint
- El frontend tiene el código para mostrar el badge pero nunca se activa

## 🟡 Endpoint debug_quota público
- `GET/POST /api/debug/quota/` tiene `AllowAny` — riesgo de seguridad
- Eliminar o proteger antes de escalar usuarios

## 🟡 Caption "Sin contenido" en posts
- Verificar con Gemini reseteado

## 🟡 Agente muestra email en vez de nombre
- Campo `agenteNombre` en DB tiene email en vez de nombre real

## 🟡 Corte de páginas en PDF
- Texto se corta entre páginas
- Agregar `page-break-inside: avoid` en los 5 templates PDF

## 🟡 Probar pagos Mercado Pago en producción
- Flujo completo de compra de plan y recursos adicionales sin probar en prod

# LeadBook - Admin API & WebSocket Documentation

Esta documentación describe la nueva infraestructura para la gestión de APIs, Tracking de Requests, Limits y Eventos en Tiempo Real implementada para el Admin Dashboard.

## Autenticación
Todos los endpoints REST (`/api/admin/*`) requieren un JWT válido de un usuario con permisos de administrador (`is_staff=True`).
Incluir el header: `Authorization: Bearer <TOKEN>`.

## REST API Endpoints

### 1. Estadísticas Globales
`GET /api/admin/stats/`
Retorna contadores de usuarios (totales, free, paid), requests de hoy y del mes, estado del Pool de APIs, y el top 5 de usuarios y errores del día.

### 2. Gestión del Pool de APIs (API Keys)
`GET /api/admin/api-keys/?service={service}&status={status}`
Lista las API Keys. Soporta filtros por servicio (`gemini`, `elevenlabs`, `uploadpost`) y estado (`available`, `assigned`, `exhausted`, `dead`, `disabled`).

`POST /api/admin/api-keys/create/`
Crea una nueva API Key en el pool.
**Body:**
```json
{
  "service": "gemini",
  "api_key": "AIzaSy...",
  "daily_limit": 1500
}
```

`PATCH /api/admin/api-keys/<id>/`
Actualiza el estado, límite diario o notas internas de una key.

`DELETE /api/admin/api-keys/<id>/`
Elimina la key del sistema (liberando al usuario si la tuviera asignada).

`POST /api/admin/api-keys/<id>/test/`
Fuerza un **Health Check manual** hacia la API externa y actualiza su estado.

`POST /api/admin/api-keys/<id>/reassign/`
Si la key está asignada a un usuario, se la quita, la devuelve al pool, y le asigna una nueva key disponible al usuario automáticamente.

### 3. Gestión de Usuarios
`GET /api/admin/users/`
Lista paginada de todos los usuarios registrados con banderas de baneo y actividad.

`GET /api/admin/users/<id>/`
Devuelve el detalle del usuario, las keys que tiene asignadas actualmente y el historial reciente de sus logs de requests.

`POST /api/admin/users/<id>/ban/`
Banea al usuario. Le quita las keys asignadas y lo bloquea del sistema. Requiere `{"reason": "Motivo"}` en el body.

`POST /api/admin/users/<id>/unban/`
Desbanea al usuario. Si es usuario Free, le asigna nuevas keys inmediatamente.

### 4. Tracking y Alertas
`GET /api/admin/requests/`
Lista cronológica de todas las llamadas API realizadas por los usuarios (incluye éxito, tiempo de respuesta en milisegundos, y errores).

`GET /api/admin/alerts/`
Lista todas las alertas de sistema no leídas (por ejemplo, "Key agotada", "Pool vacío", "Alerta de consumo").
`PATCH /api/admin/alerts/`
Permite marcar alertas como leídas enviando un listado de IDs en el body `{"ids": [1, 2, 3]}`.

`GET /api/admin/health/`
Devuelve el porcentaje global de salud de las APIs integradas.

---

## WebSocket - Eventos en Tiempo Real

**Endpoint:** `wss://tu-dominio.com/ws/admin/live/`

Los clientes conectados a este WebSocket recibirán eventos push desde el backend en tiempo real cada vez que suceda una acción de interés.

### Formato del Mensaje
```json
{
  "type": "request_made",
  "data": {
    "user": "usuario@email.com",
    "service": "gemini",
    "action": "generar_guion",
    "success": true,
    "time_ms": 1240
  }
}
```

### Eventos Emitidos Actualmente
- `request_made`: Se emite automáticamente tras finalizar una llamada a una API externa mediante el decorador `@track_api_call`.

---

## Celery Tasks (Mantenimiento Automático)
1. **health_check_all_keys()**: Verifica el estado de las APIs. Marca las fallidas y las rota si superan los intentos máximos.
2. **reset_daily_counters()**: A medianoche (UTC), limpia los requests del día para las quotas de usuario y las API keys.
3. **reset_monthly_counters()**: El día 1 de cada mes limpia los contadores mensuales.

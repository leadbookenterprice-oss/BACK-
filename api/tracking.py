import time
import functools
# pyrefly: ignore [missing-import]
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from api.models import APIKey, APIRequestLog, UserAPIQuota, AdminAlert
from api.services.pool_service import APIPoolService

def emit_ws_event(event_data):
    """Envía un evento al consumer de WebSockets del Admin Dashboard"""
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                event_data
            )
        except Exception as e:
            # Silencioso, no queremos romper el flujo si Redis/Channels falla
            pass

def track_api_call(service, action=''):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extraer usuario, asumiendo que el agente se pasa como kwarg 'agente'
            # o que el primer arg es request/user si aplica.
            agente = kwargs.get('agente', None)
            
            # Si no hay agente asignado al request (ej. llamadas de cron o internas)
            # bypass el tracking completo o usa una key de sistema.
            if not agente:
                return func(*args, **kwargs)

            # Verificar cuota
            from api.models import Servicio
            servicio_obj, _ = Servicio.objects.get_or_create(nombre=service)
            quota, _ = UserAPIQuota.objects.get_or_create(user=agente, servicio=servicio_obj)
            if quota.is_blocked:
                raise Exception(f"Usuario bloqueado para el servicio {service}: {quota.blocked_reason}")
                
            if quota.requests_today >= quota.user_daily_limit:
                raise Exception(f"Límite diario alcanzado para el servicio {service}")

            # Buscar la API Key (si falla pool legacy, no bloquear ejecución local)
            key_str = None
            key_obj = None
            try:
                from api.pool_manager import get_api_key
                key_str = get_api_key(agente, service)
                if key_str:
                    key_obj = APIKey.objects.filter(api_key=key_str).first()
            except Exception as e:
                # En local/dev puede haber módulos legacy no disponibles.
                # No frenamos la operación: la función puede tener fallback por env.
                print(f"[TRACKING] WARN pool unavailable for {service}: {type(e).__name__}: {e}", flush=True)

            start_time = time.time()
            success = False
            status_code = None
            error_msg = None
            response = None
            
            try:
                # Ejecutar la llamada real
                response = func(*args, **kwargs)
                success = True
                status_code = 200 # Asumimos 200 si no lanzó excepción
            except Exception as e:
                success = False
                error_msg = str(e)
                status_code = 500
                
                # Penalizar key si existe
                if key_obj:
                    key_obj.error_count += 1
                    if key_obj.error_count >= 10: # Threshold
                        APIPoolService.mark_key_dead(key_obj)
                    else:
                        key_obj.save()
                raise e
            finally:
                elapsed_ms = int((time.time() - start_time) * 1000)
                
                # Actualizar contadores
                quota.requests_today += 1
                quota.requests_this_month += 1
                quota.save()
                
                if key_obj:
                    key_obj.requests_today += 1
                    key_obj.requests_this_month += 1
                    key_obj.total_requests += 1
                    key_obj.last_used_at = timezone.now()
                    key_obj.save()
                    
                    # Alertas de uso
                    key_daily_limit = getattr(key_obj, 'google_daily_limit', 0) or 0
                    if key_daily_limit and key_obj.requests_today >= (key_daily_limit * 0.8):
                        AdminAlert.objects.get_or_create(
                            type='quota_warning',
                            severity='warning',
                            related_api_key=key_obj,
                            creado_en__date=timezone.now().date(),
                            defaults={
                                'title': f'Key al {int((key_obj.requests_today/key_daily_limit)*100)}% de uso diario',
                                'message': f'La key de {service} asignada a {agente.email} está por agotarse.'
                            }
                        )

                # Guardar log solo si tenemos una key en la DB
                if key_obj:
                    APIRequestLog.objects.create(
                        api_key=key_obj,
                        user=agente,
                        servicio=servicio_obj,
                        endpoint=func.__name__,
                        method='POST',
                        success=success,
                        status_code=status_code,
                        response_time_ms=elapsed_ms,
                        error_message=error_msg,
                    )
                
                # Emitir WebSocket
                emit_ws_event({
                    "type": "api_request_made",
                    "data": {
                        "user": agente.email,
                        "service": service,
                        "action": action,
                        "success": success,
                        "time_ms": elapsed_ms
                    }
                })

            return response
        return wrapper
    return decorator

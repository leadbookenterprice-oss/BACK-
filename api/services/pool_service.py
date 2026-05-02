from django.utils import timezone
from api.models import APIKey, AdminAlert

class APIPoolService:
    @staticmethod
    def assign_keys_to_user(user):
        """Asigna una key de cada servicio (si está disponible) al usuario."""
        servicios = ['gemini', 'elevenlabs', 'uploadpost']
        asignadas = []
        
        for s in servicios:
            # Check si ya tiene una asignada
            if APIKey.objects.filter(assigned_to=user, servicio=s).exists():
                continue
                
            key = APIKey.objects.filter(status='available', servicio=s).first()
            if key:
                key.status = 'assigned'
                key.assigned_to = user
                key.assigned_at = timezone.now()
                key.save()
                asignadas.append(s)
            else:
                AdminAlert.objects.create(
                    type='quota_warning',
                    severity='critical',
                    title=f'No hay keys disponibles para {s}',
                    message=f'Se intentó asignar una key de {s} al usuario {user.email} pero el pool está vacío.',
                    related_user=user
                )
        return asignadas

    @staticmethod
    def release_keys_from_user(user):
        """Libera todas las keys asignadas a un usuario."""
        keys = APIKey.objects.filter(assigned_to=user)
        for key in keys:
            key.status = 'available'
            key.assigned_to = None
            key.assigned_at = None
            key.requests_today = 0
            key.save()

    @staticmethod
    def rotate_key(user, service):
        """Libera la key actual (si la hay y está muerta/exhausta) y asigna una nueva."""
        old_key = APIKey.objects.filter(assigned_to=user, servicio=service).first()
        if old_key:
            if old_key.status not in ['dead', 'exhausted']:
                old_key.status = 'available'
            old_key.assigned_to = None
            old_key.save()
            
        new_key = APIKey.objects.filter(status='available', servicio=service).first()
        if new_key:
            new_key.status = 'assigned'
            new_key.assigned_to = user
            new_key.assigned_at = timezone.now()
            new_key.save()
            return new_key
        else:
            AdminAlert.objects.create(
                type='quota_warning',
                severity='critical',
                title=f'Fallo al rotar key de {service}',
                message=f'No se pudo asignar una nueva key a {user.email} porque el pool está vacío.',
                related_user=user,
                related_api_key=old_key
            )
            return None

    @staticmethod
    def mark_key_dead(key):
        """Marca una key como muerta y la desvincula."""
        user = key.assigned_to
        key.status = 'dead'
        key.assigned_to = None
        key.save()
        
        AdminAlert.objects.create(
            type='api_dead',
            severity='critical',
            title=f'Key muerta: {key.servicio}',
            message=f'La key ID {key.id} ha sido marcada como muerta. Revisa el log de errores.',
            related_api_key=key
        )
        
        if user:
            APIPoolService.rotate_key(user, key.servicio)

    @staticmethod
    def get_pool_stats():
        """Devuelve el conteo de keys por estado y servicio."""
        from django.db.models import Count
        stats = list(APIKey.objects.values('servicio', 'status').annotate(total=Count('id')))
        # Estructurar resultado
        result = {}
        for s in stats:
            serv = s['servicio']
            if serv not in result:
                result[serv] = {'available': 0, 'assigned': 0, 'exhausted': 0, 'dead': 0, 'disabled': 0}
            result[serv][s['status']] = s['total']
        return result

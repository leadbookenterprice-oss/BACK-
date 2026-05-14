"""
pool_service.py — LeadBook v2.0
Gestión del pool de APIs usando el nuevo schema:
  - UserAPIAssignment (reemplaza APIBundle + APIBundleAssignment + BundleAPIExtra)
  - Servicio (reemplaza strings sueltos 'gemini', 'elevenlabs', etc.)
  - AdminAlert (misma tabla, campos renombrados en v2)
"""
from django.utils import timezone
from django.db import transaction
from api.models import APIKey, UserAPIAssignment, Servicio, AdminAlert, UserAPIQuota


SERVICIOS_CRITICOS = ['gemini', 'elevenlabs', 'uploadpost']


class APIPoolService:

    # ── Asignación ────────────────────────────────────────────────────────────

    @staticmethod
    def assign_keys_to_user(user):
        """
        Asigna una APIKey primaria por servicio crítico al usuario recién creado.
        Crea también el UserAPIQuota correspondiente.
        Devuelve la lista de servicios asignados correctamente.
        """
        asignados = []
        for nombre_servicio in SERVICIOS_CRITICOS:
            servicio = Servicio.objects.filter(nombre=nombre_servicio, activo=True).first()
            if not servicio:
                continue

            # Ya tiene asignación primaria activa → skip
            if UserAPIAssignment.objects.filter(
                user=user, servicio=servicio, is_primary=True, activo=True
            ).exists():
                asignados.append(nombre_servicio)
                continue

            # IDs de keys ya usadas por este usuario en este servicio
            keys_en_uso = UserAPIAssignment.objects.filter(
                user=user, servicio=servicio
            ).values_list('apikey_id', flat=True)

            key = APIKey.objects.filter(
                servicio=servicio,
                status='available'
            ).exclude(id__in=keys_en_uso).first()

            if not key:
                AdminAlert.objects.create(
                    tipo='assign_failed',
                    severidad='critical',
                    titulo=f'Sin keys disponibles: {nombre_servicio}',
                    mensaje=f'No se pudo asignar key de {nombre_servicio} a {user.email}. Pool vacío.',
                    related_user=user,
                )
                continue

            # Crear asignación primaria
            UserAPIAssignment.objects.create(
                user=user,
                apikey=key,
                servicio=servicio,
                is_primary=True,
                activo=True,
            )

            # Marcar key como asignada
            key.status = 'assigned'
            key.save(update_fields=['status', 'updated_at'])

            # Crear/actualizar quota
            quota, created = UserAPIQuota.objects.get_or_create(
                user=user,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                }
            )

            asignados.append(nombre_servicio)

        return asignados

    @staticmethod
    def release_keys_from_user(user):
        """
        Libera TODAS las asignaciones activas del usuario y devuelve las keys al pool.
        Se llama al eliminar/suspender un usuario.
        """
        assignments = UserAPIAssignment.objects.filter(user=user, activo=True)
        for asig in assignments:
            asig.activo = False
            asig.save(update_fields=['activo', 'updated_at'])

            key = asig.apikey
            otras = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
            if not otras:
                key.status = 'available'
                key.save(update_fields=['status', 'updated_at'])

    @staticmethod
    def release_primary_key(user, nombre_servicio):
        """Libera la key primaria de un servicio específico."""
        servicio = Servicio.objects.filter(nombre=nombre_servicio).first()
        if not servicio:
            return False

        asig = UserAPIAssignment.objects.filter(
            user=user, servicio=servicio, is_primary=True, activo=True
        ).first()

        if not asig:
            return False

        asig.activo = False
        asig.save(update_fields=['activo', 'updated_at'])

        key = asig.apikey
        otras = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
        if not otras:
            key.status = 'available'
            key.save(update_fields=['status', 'updated_at'])

        return True

    @staticmethod
    def add_extra_key(user, nombre_servicio, pago=None):
        """
        Asigna una APIKey extra (no primaria) al usuario.
        Se usa al completar un pago de 'extra_gemini', 'extra_elevenlabs', etc.
        Devuelve la asignación creada o None si no hay stock.
        """
        with transaction.atomic():
            servicio = Servicio.objects.filter(nombre=nombre_servicio, activo=True).first()
            if not servicio:
                return None

            keys_en_uso = UserAPIAssignment.objects.filter(
                user=user, servicio=servicio
            ).values_list('apikey_id', flat=True)

            key = APIKey.objects.select_for_update().filter(
                servicio=servicio,
                status='available'
            ).exclude(id__in=keys_en_uso).first()

            if not key:
                AdminAlert.objects.create(
                    tipo='assign_failed',
                    severidad='warning',
                    titulo=f'Sin stock extra: {nombre_servicio}',
                    mensaje=f'No hay keys extra disponibles de {nombre_servicio} para {user.email}.',
                    related_user=user,
                )
                return None

            asig = UserAPIAssignment.objects.create(
                user=user,
                apikey=key,
                servicio=servicio,
                is_primary=False,
                activo=True,
                pago=pago,
            )

            key.status = 'assigned'
            key.save(update_fields=['status', 'updated_at'])

            quota, _ = UserAPIQuota.objects.get_or_create(
                user=user,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                }
            )
            quota.recalcular_limite()
            quota.is_blocked = False
            quota.blocked_reason = None
            quota.save(update_fields=['user_daily_limit', 'is_blocked', 'blocked_reason', 'updated_at'])

            return asig

    # ── Reparación ────────────────────────────────────────────────────────────

    @staticmethod
    def repair_user_apis(user):
        """
        Detecta qué servicios le faltan al usuario y los asigna del pool.
        Devuelve lista de servicios reparados.
        """
        repaired = []
        for nombre_servicio in SERVICIOS_CRITICOS:
            servicio = Servicio.objects.filter(nombre=nombre_servicio, activo=True).first()
            if not servicio:
                continue

            tiene_activa = UserAPIAssignment.objects.filter(
                user=user, servicio=servicio, is_primary=True, activo=True
            ).exists()

            if tiene_activa:
                continue

            # Intentar asignar
            result = APIPoolService.assign_keys_to_user.__wrapped__(user) \
                if hasattr(APIPoolService.assign_keys_to_user, '__wrapped__') \
                else None

            # Llamada directa simplificada para reparación
            keys_en_uso = UserAPIAssignment.objects.filter(
                user=user, servicio=servicio
            ).values_list('apikey_id', flat=True)

            key = APIKey.objects.filter(
                servicio=servicio, status='available'
            ).exclude(id__in=keys_en_uso).first()

            if key:
                UserAPIAssignment.objects.create(
                    user=user, apikey=key, servicio=servicio,
                    is_primary=True, activo=True,
                )
                key.status = 'assigned'
                key.save(update_fields=['status', 'updated_at'])
                repaired.append(nombre_servicio)
            else:
                AdminAlert.objects.create(
                    tipo='assign_failed',
                    severidad='warning',
                    titulo=f'Sin stock para reparar: {nombre_servicio}',
                    mensaje=f'No hay keys disponibles de {nombre_servicio} para {user.email}.',
                    related_user=user,
                )

        return repaired

    @staticmethod
    def mark_key_dead(key):
        """Marca una key como muerta y alerta al admin."""
        key.status = 'dead'
        key.save(update_fields=['status', 'updated_at'])

        AdminAlert.objects.create(
            tipo='api_dead',
            severidad='critical',
            titulo=f'Key muerta: {key.servicio.nombre}',
            mensaje=f'La key ID {key.id} ({key.label or key.api_key[:12]}) fue marcada como muerta.',
            related_api_key=key,
        )

        # Intentar reparar usuarios afectados
        afectados = UserAPIAssignment.objects.filter(
            apikey=key, activo=True
        ).select_related('user')
        for asig in afectados:
            asig.activo = False
            asig.save(update_fields=['activo', 'updated_at'])
            APIPoolService.repair_user_apis(asig.user)

    # ── Stats ─────────────────────────────────────────────────────────────────

    @staticmethod
    def get_pool_stats():
        """Resumen del estado del pool."""
        from django.db.models import Count
        key_stats = list(
            APIKey.objects.values('servicio__nombre', 'status').annotate(total=Count('id'))
        )
        return {'keys': key_stats}

    @staticmethod
    def get_bundle_stats():
        """Alias de compatibilidad — devuelve stats de keys por servicio."""
        from django.db.models import Count
        disponibles = {}
        asignadas = {}
        for s in SERVICIOS_CRITICOS:
            servicio = Servicio.objects.filter(nombre=s).first()
            if not servicio:
                continue
            disponibles[s] = APIKey.objects.filter(servicio=servicio, status='available').count()
            asignadas[s] = UserAPIAssignment.objects.filter(servicio=servicio, activo=True).count()
        return {'disponibles': disponibles, 'asignadas': asignadas}

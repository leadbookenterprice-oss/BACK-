"""
pool_service.py — LeadBook v2.0
Gestión del pool de APIs usando el nuevo schema:
  - UserAPIAssignment (reemplaza APIBundle + APIBundleAssignment + BundleAPIExtra)
  - Servicio (reemplaza strings sueltos 'gemini', 'elevenlabs', etc.)
  - AdminAlert (misma tabla, campos renombrados en v2)
"""
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q
from api.models import APIKey, UserAPIAssignment, Servicio, AdminAlert, UserAPIQuota


SERVICE_DEFAULTS = {
    'gemini': {
        'descripcion': 'Google Gemini AI Studio',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'elevenlabs': {
        'descripcion': 'ElevenLabs',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'uploadpost': {
        'descripcion': 'UploadPost',
        'default_daily_limit': 999999,
        'default_monthly_limit': 10,
        'extra_increment': 10,
    },
    'cerebras': {
        'descripcion': 'Cerebras',
        'default_daily_limit': 1710,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'groq': {
        'descripcion': 'Groq',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'openrouter': {
        'descripcion': 'OpenRouter',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'nvidia': {
        'descripcion': 'NVIDIA NIM',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'huggingface': {
        'descripcion': 'Hugging Face',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'mistral': {
        'descripcion': 'Mistral AI',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'cohere': {
        'descripcion': 'Cohere',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'sambanova': {
        'descripcion': 'SambaNova',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'deepseek': {
        'descripcion': 'DeepSeek',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'cloudflare_workers_ai': {
        'descripcion': 'Cloudflare Workers AI',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'github_models': {
        'descripcion': 'GitHub Models',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
    },
    'cloudinary': {
        'descripcion': 'Cloudinary',
        'default_daily_limit': 999999,
        'default_monthly_limit': None,
        'extra_increment': 1,
    },
}

AI_POOL_SERVICES = tuple(
    name for name in SERVICE_DEFAULTS
    if name not in {'uploadpost', 'cloudinary'}
)
CONTENT_BUNDLE_SERVICES = ('cerebras',)

SERVICIOS_CRITICOS = list(CONTENT_BUNDLE_SERVICES)
CEREBRAS_STARTER_SHARED_USERS_PER_KEY = 57
CEREBRAS_SHARED_PLANS = {'free', 'starter'}

PLAN_API_COUNTS = {
    'free': {'cerebras': 1},
    'starter': {'cerebras': 1},
    'pro': {'cerebras': 3},
    'scale': {'cerebras': 5},
    'business': {'cerebras': 5},
}

COMPATIBILITY_API_COUNTS = {}


def _desired_api_counts_for_plan(plan):
    counts = dict(COMPATIBILITY_API_COUNTS)
    counts.update(PLAN_API_COUNTS.get(str(plan or 'starter').lower(), PLAN_API_COUNTS['starter']))
    return counts


def _is_staff_account(user):
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _uses_shared_cerebras(nombre_servicio, plan):
    return (
        str(nombre_servicio or '').strip().lower() == 'cerebras'
        and str(plan or 'starter').strip().lower() in CEREBRAS_SHARED_PLANS
    )


def _active_key_assignments_count_filter():
    return Q(assignments__activo=True)


def ensure_core_services():
    """Crea el catálogo mínimo de servicios para que el pool pueda asignar keys."""
    for nombre, defaults in SERVICE_DEFAULTS.items():
        Servicio.objects.update_or_create(
            nombre=nombre,
            defaults={
                'descripcion': defaults['descripcion'],
                'activo': True,
                'default_daily_limit': defaults['default_daily_limit'],
                'default_monthly_limit': defaults['default_monthly_limit'],
                'extra_increment': defaults['extra_increment'],
            },
        )


def _create_assign_failed_alert(user, service_name, missing_count):
    title = f'Sin keys disponibles: {service_name}'
    if AdminAlert.objects.filter(
        tipo='assign_failed',
        related_user=user,
        titulo=title,
        creado_en__date=timezone.now().date(),
    ).exists():
        return
    AdminAlert.objects.create(
        tipo='assign_failed',
        severidad='critical',
        titulo=title,
        mensaje=(
            f'No se pudieron asignar {missing_count} key(s) de {service_name} '
            f'a {user.email}. Pool vacío.'
        ),
        related_user=user,
    )


class APIPoolService:

    # ── Asignación ────────────────────────────────────────────────────────────

    @staticmethod
    def assign_keys_to_user(user):
        """
        Asigna al usuario las APIs requeridas por su plan.
        Crea también el UserAPIQuota correspondiente.
        Devuelve la lista de servicios que tienen al menos una key activa o fueron asignados.
        """
        if _is_staff_account(user):
            return []

        asignados = []
        ensure_core_services()
        desired_counts = _desired_api_counts_for_plan(getattr(user, 'plan_nombre', 'starter'))
        plan_name = str(getattr(user, 'plan_nombre', 'starter') or 'starter').strip().lower()

        for nombre_servicio, desired_count in desired_counts.items():
            servicio = Servicio.objects.filter(nombre=nombre_servicio, activo=True).first()
            if not servicio:
                continue

            active_assignments = UserAPIAssignment.objects.filter(
                user=user,
                servicio=servicio,
                activo=True,
                apikey__status__in=['assigned', 'available'],
            )
            active_count = active_assignments.count()
            if active_count >= desired_count:
                asignados.append(nombre_servicio)
                quota, _ = UserAPIQuota.objects.get_or_create(
                    user=user,
                    servicio=servicio,
                    defaults={
                        'user_daily_limit': servicio.default_daily_limit,
                        'user_monthly_limit': servicio.default_monthly_limit,
                    }
                )
                quota.recalcular_limite(plan=getattr(user, 'plan_nombre', 'starter'))
                continue

            # IDs de keys ya usadas por este usuario en este servicio
            keys_en_uso = UserAPIAssignment.objects.filter(
                user=user, servicio=servicio
            ).values_list('apikey_id', flat=True)

            missing_count = desired_count - active_count
            assigned_any = active_count > 0
            for _ in range(missing_count):
                if _uses_shared_cerebras(nombre_servicio, plan_name):
                    key = (
                        APIKey.objects
                        .filter(servicio=servicio, status__in=['available', 'assigned'])
                        .exclude(id__in=keys_en_uso)
                        .annotate(active_assignments_count=Count('assignments', filter=_active_key_assignments_count_filter()))
                        .filter(active_assignments_count__lt=CEREBRAS_STARTER_SHARED_USERS_PER_KEY)
                        .order_by('active_assignments_count', 'requests_today', 'id')
                        .first()
                    )
                else:
                    key = APIKey.objects.filter(
                        servicio=servicio,
                        status='available'
                    ).exclude(id__in=keys_en_uso).order_by('requests_today', 'id').first()

                if not key:
                    _create_assign_failed_alert(user, nombre_servicio, desired_count - active_count)
                    break

                has_primary = UserAPIAssignment.objects.filter(
                    user=user,
                    servicio=servicio,
                    is_primary=True,
                    activo=True,
                ).exists()

                # Crear asignación: una primaria y el resto como cupo del plan.
                UserAPIAssignment.objects.create(
                    user=user,
                    apikey=key,
                    servicio=servicio,
                    is_primary=not has_primary,
                    activo=True,
                )

                key.status = 'assigned'
                key.save(update_fields=['status', 'updated_at'])
                assigned_any = True
                active_count += 1
                keys_en_uso = list(keys_en_uso) + [key.id]

            quota, created = UserAPIQuota.objects.get_or_create(
                user=user,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                }
            )
            quota.recalcular_limite(plan=getattr(user, 'plan_nombre', 'starter'))

            if assigned_any:
                asignados.append(nombre_servicio)

        return asignados

    assign_apis_to_agent = assign_keys_to_user

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
        if _is_staff_account(user):
            return None

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
        return APIPoolService.assign_keys_to_user(user)

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


def assign_apis_to_agent(agent):
    """Función pública para asignar APIs del pool según el plan del usuario."""
    return APIPoolService.assign_keys_to_user(agent)

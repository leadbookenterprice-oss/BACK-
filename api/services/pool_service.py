"""
Pool interno de APIs LeadBook.

Las API keys de IA no se asignan a usuarios: pertenecen a LeadBook.
UploadPost es la unica excepcion: cada usuario necesita una key vinculada.
"""

from django.utils import timezone

from api.models import APIKey, AdminAlert, Servicio, UserAPIAssignment, UserAPIQuota


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
        'default_daily_limit': 1000000,
        'default_monthly_limit': None,
        'extra_increment': 1000000,
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

AI_POOL_SERVICES = tuple(name for name in SERVICE_DEFAULTS if name not in {'uploadpost', 'cloudinary'})
CONTENT_BUNDLE_SERVICES = ('cerebras',)
SERVICIOS_CRITICOS = list(CONTENT_BUNDLE_SERVICES)


def _is_staff_account(user):
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def ensure_core_services():
    """Crea/actualiza el catalogo minimo de servicios del pool."""
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


class APIPoolService:
    @staticmethod
    def ensure_uploadpost_assignment(user):
        """Asigna exactamente una key UploadPost activa por usuario si hay stock."""
        if not user or _is_staff_account(user):
            return None

        ensure_core_services()
        servicio = Servicio.objects.filter(nombre__iexact='uploadpost', activo=True).first()
        if not servicio:
            return None

        active = (
            UserAPIAssignment.objects
            .filter(user=user, servicio=servicio, activo=True, apikey__isnull=False)
            .select_related('apikey')
            .order_by('-is_primary', 'assigned_at')
            .first()
        )
        if active and active.apikey_id:
            if active.apikey.status == 'available':
                active.apikey.status = 'assigned'
                active.apikey.save(update_fields=['status', 'updated_at'])
            return active

        assigned_key_ids = UserAPIAssignment.objects.filter(
            servicio=servicio,
            activo=True,
        ).values_list('apikey_id', flat=True)

        key = (
            APIKey.objects
            .filter(servicio=servicio, status='available')
            .exclude(id__in=assigned_key_ids)
            .order_by('requests_this_month', 'requests_today', 'id')
            .first()
        )
        if not key:
            return None

        assignment = UserAPIAssignment.objects.create(
            user=user,
            apikey=key,
            servicio=servicio,
            is_primary=True,
            activo=True,
        )
        key.status = 'assigned'
        key.save(update_fields=['status', 'updated_at'])
        return assignment

    @staticmethod
    def ensure_user_quotas(user):
        """
        Crea/actualiza cuotas por usuario.
        Solo UploadPost se asigna a usuario; las APIs de IA quedan en pool global.
        """
        if not user or _is_staff_account(user):
            return []

        ensure_core_services()
        touched = []
        for servicio in Servicio.objects.filter(activo=True):
            quota, _ = UserAPIQuota.objects.get_or_create(
                user=user,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                },
            )
            quota.recalcular_limite(plan=getattr(user, 'plan_nombre', 'starter'))
            touched.append(servicio.nombre)
        APIPoolService.ensure_uploadpost_assignment(user)
        return touched

    @staticmethod
    def assign_keys_to_user(user):
        """Compatibilidad legacy: ya no asigna keys; solo asegura cuotas."""
        return APIPoolService.ensure_user_quotas(user)

    assign_apis_to_agent = assign_keys_to_user

    @staticmethod
    def release_keys_from_user(user):
        """Libera la asignacion UploadPost del usuario."""
        assignments = UserAPIAssignment.objects.filter(
            user=user,
            activo=True,
            servicio__nombre__iexact='uploadpost',
        ).select_related('apikey')
        for assignment in assignments:
            assignment.activo = False
            assignment.save(update_fields=['activo', 'updated_at'])
            key = assignment.apikey
            if key and key.status == 'assigned' and not UserAPIAssignment.objects.filter(apikey=key, activo=True).exists():
                key.status = 'available'
                key.save(update_fields=['status', 'updated_at'])

    @staticmethod
    def release_primary_key(user, nombre_servicio):
        """Compatibilidad legacy."""
        if str(nombre_servicio or '').strip().lower() != 'uploadpost':
            return False
        before = UserAPIAssignment.objects.filter(
            user=user,
            servicio__nombre__iexact='uploadpost',
            activo=True,
        ).count()
        APIPoolService.release_keys_from_user(user)
        return bool(before)

    @staticmethod
    def add_extra_key(user, nombre_servicio, pago=None):
        """Solo UploadPost se vincula por usuario; no hay extras de IA."""
        APIPoolService.ensure_user_quotas(user)
        if str(nombre_servicio or '').strip().lower() == 'uploadpost':
            return APIPoolService.ensure_uploadpost_assignment(user)
        return None

    @staticmethod
    def repair_user_apis(user):
        """Compatibilidad: no repara asignaciones; solo asegura cuotas."""
        return APIPoolService.ensure_user_quotas(user)

    @staticmethod
    def mark_key_dead(key):
        key.status = 'dead'
        key.save(update_fields=['status', 'updated_at'])
        UserAPIAssignment.objects.filter(apikey=key, activo=True).update(activo=False, updated_at=timezone.now())
        AdminAlert.objects.create(
            tipo='api_dead',
            severidad='critical',
            titulo=f'Key muerta: {key.servicio.nombre}',
            mensaje=f'La key ID {key.id} ({key.label or key.api_key[:12]}) fue marcada como muerta.',
            related_api_key=key,
        )

    @staticmethod
    def get_pool_stats():
        from django.db.models import Count
        key_stats = list(APIKey.objects.values('servicio__nombre', 'status').annotate(total=Count('id')))
        return {'keys': key_stats}

    @staticmethod
    def get_bundle_stats():
        disponibles = {}
        en_uso = {}
        for service_name in SERVICIOS_CRITICOS:
            servicio = Servicio.objects.filter(nombre=service_name).first()
            if not servicio:
                continue
            disponibles[service_name] = APIKey.objects.filter(servicio=servicio, status='available').count()
            en_uso[service_name] = APIKey.objects.filter(servicio=servicio, status='in_use').count()
        return {'disponibles': disponibles, 'en_uso': en_uso}


def assign_apis_to_agent(agent):
    """Compatibilidad publica: no asigna keys; asegura cuotas."""
    return APIPoolService.ensure_user_quotas(agent)

import os

from django.db import migrations, models


SERVICE_DEFAULTS = {
    'gemini': {
        'descripcion': 'Google Gemini',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
        'env': 'GEMINI_API_KEY',
    },
    'elevenlabs': {
        'descripcion': 'ElevenLabs',
        'default_daily_limit': 1500,
        'default_monthly_limit': None,
        'extra_increment': 1500,
        'env': 'ELEVENLABS_API_KEY',
    },
    'uploadpost': {
        'descripcion': 'UploadPost',
        'default_daily_limit': 999999,
        'default_monthly_limit': 10,
        'extra_increment': 10,
        'env': 'UPLOADPOST_API_KEY',
    },
    'cloudinary': {
        'descripcion': 'Cloudinary',
        'default_daily_limit': 999999,
        'default_monthly_limit': None,
        'extra_increment': 1,
        'env': '',
    },
}


PLAN_API_COUNTS = {
    'free': {'gemini': 1, 'elevenlabs': 1, 'uploadpost': 1},
    'starter': {'gemini': 1, 'elevenlabs': 1, 'uploadpost': 1},
    'pro': {'gemini': 3, 'elevenlabs': 3, 'uploadpost': 1},
    'scale': {'gemini': 5, 'elevenlabs': 5, 'uploadpost': 1},
    'business': {'gemini': 5, 'elevenlabs': 5, 'uploadpost': 1},
}


def _env_keys(name):
    raw = os.environ.get(name, '')
    if not raw:
        return []
    normalized = raw.replace('\r', '\n').replace(',', '\n')
    return [item.strip() for item in normalized.split('\n') if item.strip()]


def _sanitize_json_value(value):
    if isinstance(value, str):
        return None if value.strip().lower().startswith('data:') else value
    if isinstance(value, list):
        cleaned = [_sanitize_json_value(item) for item in value]
        return [item for item in cleaned if item is not None]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            sanitized = _sanitize_json_value(item)
            if sanitized is not None:
                cleaned[key] = sanitized
        return cleaned
    return value


def _assign_available_keys(apps):
    Agent = apps.get_model('api', 'Agent')
    Servicio = apps.get_model('api', 'Servicio')
    APIKey = apps.get_model('api', 'APIKey')
    UserAPIAssignment = apps.get_model('api', 'UserAPIAssignment')
    UserAPIQuota = apps.get_model('api', 'UserAPIQuota')

    users = Agent.objects.filter(is_active=True, eliminado_en__isnull=True, is_staff=False).order_by('id')
    for user in users:
        plan = str(getattr(user, 'plan_nombre', '') or 'starter').lower()
        desired = PLAN_API_COUNTS.get(plan, PLAN_API_COUNTS['starter'])
        for service_name, desired_count in desired.items():
            servicio = Servicio.objects.filter(nombre=service_name, activo=True).first()
            if not servicio:
                continue
            quota, _ = UserAPIQuota.objects.get_or_create(
                user=user,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                },
            )
            active_count = UserAPIAssignment.objects.filter(
                user=user,
                servicio=servicio,
                activo=True,
            ).exclude(apikey__status__in=['dead', 'disabled']).count()
            missing = max(0, desired_count - active_count)
            if missing <= 0:
                continue
            used_ids = set(UserAPIAssignment.objects.filter(user=user, servicio=servicio).values_list('apikey_id', flat=True))
            for _ in range(missing):
                key = APIKey.objects.filter(servicio=servicio, status='available').exclude(id__in=used_ids).order_by('requests_today', 'id').first()
                if not key:
                    break
                has_primary = UserAPIAssignment.objects.filter(user=user, servicio=servicio, is_primary=True, activo=True).exists()
                UserAPIAssignment.objects.create(
                    user=user,
                    apikey=key,
                    servicio=servicio,
                    is_primary=not has_primary,
                    activo=True,
                )
                key.status = 'assigned'
                key.save(update_fields=['status', 'updated_at'])
                used_ids.add(key.id)
            if service_name == 'uploadpost':
                quota.user_daily_limit = 999999
                quota.user_monthly_limit = None if plan in {'pro', 'scale', 'business'} else 10
            elif service_name in {'gemini', 'elevenlabs'}:
                base = {'free': 1500, 'starter': 3000, 'pro': 7500, 'scale': 15000, 'business': 30000}.get(plan, 3000)
                extras = UserAPIAssignment.objects.filter(user=user, servicio=servicio, activo=True, is_primary=False).count()
                quota.user_daily_limit = base + (extras * servicio.extra_increment)
            quota.save(update_fields=['user_daily_limit', 'user_monthly_limit', 'updated_at'])


def forwards(apps, schema_editor):
    Agent = apps.get_model('api', 'Agent')
    ComercialAgentProfile = apps.get_model('api', 'ComercialAgentProfile')
    Listado = apps.get_model('api', 'Listado')
    Servicio = apps.get_model('api', 'Servicio')
    APIKey = apps.get_model('api', 'APIKey')

    services = {}
    for name, defaults in SERVICE_DEFAULTS.items():
        servicio, _ = Servicio.objects.update_or_create(
            nombre=name,
            defaults={
                'descripcion': defaults['descripcion'],
                'activo': True,
                'default_daily_limit': defaults['default_daily_limit'],
                'default_monthly_limit': defaults['default_monthly_limit'],
                'extra_increment': defaults['extra_increment'],
            },
        )
        services[name] = servicio
        env_name = defaults.get('env')
        if env_name:
            for idx, api_key in enumerate(_env_keys(env_name), start=1):
                APIKey.objects.get_or_create(
                    servicio=servicio,
                    api_key=api_key,
                    defaults={
                        'label': f'env:{env_name}:{idx}',
                        'status': 'available',
                        'google_daily_limit': defaults['default_daily_limit'] if name != 'uploadpost' else 999999,
                    },
                )

    Agent.objects.filter(logo_url__startswith='data:').update(logo_url=None)
    ComercialAgentProfile.objects.filter(foto_url__startswith='data:').update(foto_url=None)

    for listado in Listado.objects.exclude(datos_extra=None).only('id', 'datos_extra').iterator(chunk_size=200):
        if not isinstance(listado.datos_extra, dict):
            continue
        sanitized = _sanitize_json_value(listado.datos_extra)
        if sanitized != listado.datos_extra:
            listado.datos_extra = sanitized or {}
            listado.save(update_fields=['datos_extra'])

    _assign_available_keys(apps)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_add_agent_settings_and_notifications'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminalert',
            name='tipo',
            field=models.CharField(choices=[
                ('quota_warning', 'Quota Warning'),
                ('api_dead', 'API Muerta'),
                ('pool_low', 'Pool bajo — menos de 3 disponibles'),
                ('user_abuse', 'Abuso de usuario'),
                ('trial_token_request', 'Token solicitado'),
                ('high_error_rate', 'Alta tasa de errores'),
                ('webhook_error', 'Error en Webhook'),
                ('assign_failed', 'Fallo en asignación de APIs'),
            ], max_length=20),
        ),
        migrations.RunPython(forwards, backwards),
    ]

from django.db import migrations


SERVICE_DEFAULTS = {
    'gemini': ('Google Gemini AI Studio', 1500, None, 1500),
    'elevenlabs': ('ElevenLabs', 1500, None, 1500),
    'uploadpost': ('UploadPost', 999999, 10, 10),
    'cerebras': ('Cerebras', 1500, None, 1500),
    'groq': ('Groq', 1500, None, 1500),
    'openrouter': ('OpenRouter', 1500, None, 1500),
    'nvidia': ('NVIDIA NIM', 1500, None, 1500),
    'huggingface': ('Hugging Face', 1500, None, 1500),
    'mistral': ('Mistral AI', 1500, None, 1500),
    'cohere': ('Cohere', 1500, None, 1500),
    'sambanova': ('SambaNova', 1500, None, 1500),
    'deepseek': ('DeepSeek', 1500, None, 1500),
    'cloudflare_workers_ai': ('Cloudflare Workers AI', 1500, None, 1500),
    'github_models': ('GitHub Models', 1500, None, 1500),
    'cloudinary': ('Cloudinary', 999999, None, 1),
}


def seed_ai_provider_services(apps, schema_editor):
    Servicio = apps.get_model('api', 'Servicio')
    for nombre, (descripcion, daily_limit, monthly_limit, extra_increment) in SERVICE_DEFAULTS.items():
        Servicio.objects.update_or_create(
            nombre=nombre,
            defaults={
                'descripcion': descripcion,
                'activo': True,
                'default_daily_limit': daily_limit,
                'default_monthly_limit': monthly_limit,
                'extra_increment': extra_increment,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_lead_pipelinestage_leadevent_leadassignment_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_ai_provider_services, noop_reverse),
    ]

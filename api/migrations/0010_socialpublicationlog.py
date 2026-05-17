from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_social_publications(apps, schema_editor):
    APIRequestLog = apps.get_model('api', 'APIRequestLog')
    Servicio = apps.get_model('api', 'Servicio')
    SocialPublicationLog = apps.get_model('api', 'SocialPublicationLog')

    uploadpost = Servicio.objects.filter(nombre__iexact='uploadpost').first()
    if not uploadpost:
        return

    logs = APIRequestLog.objects.filter(servicio_id=uploadpost.id).order_by('id')
    for api_log in logs.iterator():
        request_id = f'api-log-{api_log.id}'
        obj, created = SocialPublicationLog.objects.get_or_create(
            user_id=api_log.user_id,
            provider='uploadpost',
            request_id=request_id,
            defaults={
                'servicio_id': uploadpost.id,
                'platform': 'instagram',
                'media_type': 'unknown',
                'job_id': '',
                'batch_id': '',
                'success': bool(api_log.success),
                'counted': bool(api_log.success),
                'status': 'completed' if api_log.success else 'failed',
                'caption': '',
                'media_count': 1 if api_log.success else 0,
                'payload': {
                    'source': 'api_request_log_backfill',
                    'api_request_log_id': api_log.id,
                    'endpoint': api_log.endpoint,
                    'method': api_log.method,
                },
                'response': {},
                'error_message': api_log.error_message or '',
            },
        )
        if created and api_log.creado_en:
            SocialPublicationLog.objects.filter(pk=obj.pk).update(
                creado_en=api_log.creado_en,
                actualizado_en=api_log.creado_en,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_userfieldpreset'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocialPublicationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('uploadpost', 'UploadPost'), ('meta', 'Meta Graph')], default='uploadpost', max_length=30)),
                ('platform', models.CharField(default='instagram', max_length=50)),
                ('media_type', models.CharField(default='unknown', max_length=30)),
                ('request_id', models.CharField(blank=True, db_index=True, max_length=128)),
                ('job_id', models.CharField(blank=True, db_index=True, max_length=128)),
                ('batch_id', models.CharField(blank=True, db_index=True, max_length=64)),
                ('success', models.BooleanField(default=False)),
                ('counted', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('queued', 'En cola'), ('completed', 'Completada'), ('failed', 'Fallida'), ('unknown', 'Desconocida')], default='unknown', max_length=30)),
                ('caption', models.TextField(blank=True)),
                ('media_count', models.PositiveIntegerField(default=0)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('response', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('servicio', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='social_publication_logs', to='api.servicio')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_publication_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(fields=('user', 'provider', 'request_id'), name='api_social_unique_request'),
                ],
                'indexes': [
                    models.Index(fields=['user', 'creado_en'], name='api_social_user_created_idx'),
                    models.Index(fields=['user', 'success', 'counted', 'creado_en'], name='api_social_user_count_idx'),
                    models.Index(fields=['provider', 'platform'], name='api_social_provider_idx'),
                    models.Index(fields=['batch_id', 'creado_en'], name='api_social_batch_idx'),
                ],
            },
        ),
        migrations.RunPython(backfill_social_publications, migrations.RunPython.noop),
    ]

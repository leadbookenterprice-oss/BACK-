from django.db import migrations, models
import django.db.models.deletion


def normalize_cerebras_token_budget(apps, schema_editor):
    Servicio = apps.get_model('api', 'Servicio')
    APIKey = apps.get_model('api', 'APIKey')

    servicio = Servicio.objects.filter(nombre__iexact='cerebras').first()
    if servicio:
        servicio.default_daily_limit = 1000000
        servicio.extra_increment = 1000000
        servicio.save(update_fields=['default_daily_limit', 'extra_increment'])

    APIKey.objects.filter(
        servicio__nombre__iexact='cerebras',
        google_daily_limit__lt=100000,
    ).update(google_daily_limit=1000000)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_merge_0017_cloudinary_health_0018_ai_provider_services'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='slot_last_error',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_locked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_locked_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='locked_api_slots', to='api.agent'),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_locked_listado',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='locked_api_slots', to='api.listado'),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_tokens_reset_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_tokens_today',
            field=models.IntegerField(default=0),
        ),
        migrations.AddIndex(
            model_name='apikey',
            index=models.Index(fields=['servicio', 'slot_locked_until'], name='api_apikey_servici_1b4a0d_idx'),
        ),
        migrations.AddIndex(
            model_name='apikey',
            index=models.Index(fields=['slot_locked_by', 'slot_locked_listado'], name='api_apikey_slot_lo_93e50f_idx'),
        ),
        migrations.RunPython(normalize_cerebras_token_budget, noop_reverse),
    ]

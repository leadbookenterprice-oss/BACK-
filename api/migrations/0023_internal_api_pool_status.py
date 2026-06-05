from django.db import migrations, models
from django.utils import timezone


def migrate_internal_pool_status(apps, schema_editor):
    APIKey = apps.get_model('api', 'APIKey')
    UserAPIAssignment = apps.get_model('api', 'UserAPIAssignment')
    now = timezone.now()

    UserAPIAssignment.objects.filter(activo=True).exclude(
        servicio__nombre__iexact='uploadpost',
    ).update(activo=False, updated_at=now)

    for key in APIKey.objects.filter(status='assigned'):
        has_uploadpost_assignment = UserAPIAssignment.objects.filter(
            apikey=key,
            activo=True,
            servicio__nombre__iexact='uploadpost',
        ).exists()
        if has_uploadpost_assignment:
            key.status = 'assigned'
            key.save(update_fields=['status', 'updated_at'])
            continue

        has_active_lock = bool(
            key.slot_locked_until
            and key.slot_locked_until > now
            and (key.slot_locked_by_id or key.slot_locked_listado_id)
        )
        key.status = 'in_use' if has_active_lock else 'available'
        key.save(update_fields=['status', 'updated_at'])


def reverse_internal_pool_status(apps, schema_editor):
    APIKey = apps.get_model('api', 'APIKey')
    APIKey.objects.filter(status='in_use').update(status='assigned')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_content_generation_cerebras_logs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apikey',
            name='status',
            field=models.CharField(
                choices=[
                    ('available', 'Disponible'),
                    ('assigned', 'Asignada'),
                    ('in_use', 'En uso'),
                    ('exhausted', 'Agotada hoy'),
                    ('dead', 'Muerta'),
                    ('disabled', 'Deshabilitada'),
                ],
                default='available',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_internal_pool_status, reverse_internal_pool_status),
    ]

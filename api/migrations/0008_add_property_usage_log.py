from django.db import migrations, models


def ensure_usage_log_archivado_column(apps, schema_editor):
    table_name = 'api_usagelog'
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        columns = [col.name for col in connection.introspection.get_table_description(cursor, table_name)]
        if 'archivado' in columns:
            return

        if connection.vendor == 'sqlite':
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN archivado bool NOT NULL DEFAULT 0')
        elif connection.vendor == 'postgresql':
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS archivado boolean NOT NULL DEFAULT false')
        else:
            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN archivado boolean NOT NULL DEFAULT false')


def backfill_property_usage(apps, schema_editor):
    Listado = apps.get_model('api', 'Listado')
    UsageLog = apps.get_model('api', 'UsageLog')

    logs = []
    for listado in Listado.objects.only('agente_id', 'creado_en').iterator():
        logs.append(
            UsageLog(
                agent_id=listado.agente_id,
                tipo='property',
                fecha=listado.creado_en,
                archivado=False,
            )
        )

        if len(logs) >= 1000:
            UsageLog.objects.bulk_create(logs)
            logs = []

    if logs:
        UsageLog.objects.bulk_create(logs)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_crmclient'),
    ]

    operations = [
        migrations.RunPython(ensure_usage_log_archivado_column, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='usagelog',
                    name='tipo',
                    field=models.CharField(
                        choices=[
                            ('property', 'Listado'),
                            ('ai', 'IA / Guion'),
                            ('image', 'Imagen'),
                            ('video', 'Video'),
                            ('pdf', 'PDF'),
                        ],
                        max_length=10,
                    ),
                ),
            ],
            database_operations=[]
        ),
        migrations.RunPython(backfill_property_usage, migrations.RunPython.noop),
    ]

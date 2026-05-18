from django.db import migrations, models


def migrate_free_agents_to_starter(apps, schema_editor):
    Agent = apps.get_model('api', 'Agent')
    Agent.objects.filter(plan_nombre='free').update(plan_nombre='starter')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_agent_free_trial_ends_at_agent_free_trial_started_at_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_free_agents_to_starter, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='agent',
            name='plan_nombre',
            field=models.CharField(
                choices=[
                    ('starter', 'Starter'),
                    ('pro', 'Pro'),
                    ('scale', 'Scale'),
                    ('business', 'Business'),
                ],
                default='starter',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='plan',
            name='nombre',
            field=models.CharField(
                choices=[
                    ('starter', 'Starter'),
                    ('pro', 'Pro'),
                    ('scale', 'Scale'),
                    ('business', 'Business'),
                ],
                max_length=20,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name='suscripcion',
            name='mp_status',
            field=models.CharField(
                choices=[
                    ('free', 'Sin suscripcion'),
                    ('active', 'Activa'),
                    ('paused', 'Pausada'),
                    ('cancelled', 'Cancelada'),
                    ('past_due', 'Vencida'),
                ],
                default='free',
                max_length=20,
            ),
        ),
    ]

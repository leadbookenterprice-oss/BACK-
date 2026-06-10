from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_internal_api_pool_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='supported_models',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='apikey',
            name='models_last_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='models_last_error',
            field=models.TextField(blank=True, null=True),
        ),
    ]

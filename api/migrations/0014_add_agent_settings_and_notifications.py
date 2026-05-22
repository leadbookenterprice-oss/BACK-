from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_accesscode_assigned_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='settings',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

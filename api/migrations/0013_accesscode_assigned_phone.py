from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0012_starter_trial_plan_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='accesscode',
            name='assigned_phone',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]

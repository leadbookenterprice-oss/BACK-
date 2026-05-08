from django.db import migrations
import django.db.models.fields

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_fix_daily_limits'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userapiquota',
            name='daily_limit',
            field=django.db.models.fields.IntegerField(default=1500),
        ),
    ]

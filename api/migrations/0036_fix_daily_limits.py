from django.db import migrations

def fix_daily_limits(apps, schema_editor):
    UserAPIQuota = apps.get_model('api', 'UserAPIQuota')
    limits = {'gemini': 1500, 'elevenlabs': 10000, 'uploadpost': 10}
    # Solo corregimos los que tienen el default viejo de 20
    for quota in UserAPIQuota.objects.filter(daily_limit=20):
        quota.daily_limit = limits.get(quota.service, 1500)
        quota.save()

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0035_bundleapiextra'),
    ]
    operations = [
        migrations.RunPython(fix_daily_limits, migrations.RunPython.noop),
    ]

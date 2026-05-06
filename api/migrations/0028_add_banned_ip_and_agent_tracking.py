from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_add_agent_profile_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='BannedIP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(unique=True)),
                ('banned_at', models.DateTimeField(auto_now_add=True)),
                ('reason', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='agent',
            name='last_login_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agent',
            name='last_login_user_agent',
            field=models.TextField(blank=True, null=True),
        ),
    ]

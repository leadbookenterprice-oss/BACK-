from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_apibundle_alter_apikey_unique_together_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='BannedEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(unique=True, max_length=254)),
                ('banned_at', models.DateTimeField(auto_now_add=True)),
                ('reason', models.TextField(blank=True, default='Baneado por el administrador')),
            ],
            options={
                'verbose_name': 'Email Baneado Permanentemente',
                'verbose_name_plural': 'Emails Baneados Permanentemente',
            },
        ),
    ]

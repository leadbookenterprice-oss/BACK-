from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_brandtemplate_brandtemplaterevision_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserContentPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hashtags', models.JSONField(blank=True, default=list)),
                ('emoji_density', models.CharField(choices=[('none', 'None'), ('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='medium', max_length=20)),
                ('use_emojis', models.BooleanField(default=True)),
                ('tone', models.CharField(default='premium', max_length=40)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='content_preferences', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AgentMediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('agent_photo', 'Agent Photo')], default='agent_photo', max_length=40)),
                ('cloud_name', models.CharField(max_length=120)),
                ('public_id', models.CharField(max_length=255)),
                ('resource_type', models.CharField(default='image', max_length=40)),
                ('secure_url', models.TextField(blank=True, null=True)),
                ('bytes', models.PositiveIntegerField(default=0)),
                ('format', models.CharField(blank=True, max_length=30, null=True)),
                ('folder', models.CharField(blank=True, max_length=255, null=True)),
                ('original_filename', models.CharField(blank=True, max_length=255, null=True)),
                ('version', models.CharField(blank=True, max_length=60, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_media_assets', to=settings.AUTH_USER_MODEL)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media_assets', to='api.comercialagentprofile')),
            ],
            options={
                'ordering': ['-uploaded_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agentmediaasset',
            index=models.Index(fields=['owner', 'kind', 'is_active'], name='api_agentme_owner_i_403a3e_idx'),
        ),
        migrations.AddIndex(
            model_name='agentmediaasset',
            index=models.Index(fields=['profile', 'kind', 'is_active'], name='api_agentme_profile_5efbd1_idx'),
        ),
        migrations.AddIndex(
            model_name='agentmediaasset',
            index=models.Index(fields=['cloud_name', 'public_id'], name='api_agentme_cloud_n_0922e0_idx'),
        ),
        migrations.AddConstraint(
            model_name='agentmediaasset',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True), ('kind', 'agent_photo')), fields=('profile',), name='unique_active_agent_photo_per_profile'),
        ),
    ]

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_cloudinarystoragelog_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='slot_last_rate_limit_headers',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='apikey',
            name='slot_last_rate_limit_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ContentGenerationRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pendiente'), ('running', 'En progreso'), ('waiting_slot', 'Esperando slot'), ('waiting_rate_limit', 'Esperando rate limit'), ('done', 'Lista'), ('failed', 'Fallida'), ('cancelled', 'Cancelada')], db_index=True, default='pending', max_length=30)),
                ('current_step', models.CharField(blank=True, db_index=True, max_length=30)),
                ('total_estimated_tokens', models.PositiveIntegerField(default=0)),
                ('total_actual_tokens', models.PositiveIntegerField(default=0)),
                ('requests_count', models.PositiveIntegerField(default=0)),
                ('safe_daily_limit', models.PositiveIntegerField(default=800000)),
                ('last_rate_limit_headers', models.JSONField(blank=True, default=dict)),
                ('error_code', models.CharField(blank=True, db_index=True, max_length=80)),
                ('error_message', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='content_generation_runs', to='api.apikey')),
                ('listado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_generation_runs', to='api.listado')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_generation_runs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-started_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ContentGenerationStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step', models.CharField(choices=[('pdf', 'PDF'), ('post', 'Post'), ('story', 'Story'), ('carrusel', 'Carrusel'), ('email', 'Email')], db_index=True, max_length=30)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('status', models.CharField(choices=[('pending', 'Pendiente'), ('running', 'Generando'), ('uploading', 'Subiendo'), ('waiting_rate_limit', 'Esperando rate limit'), ('done', 'Lista'), ('failed', 'Fallida'), ('skipped', 'Saltada')], db_index=True, default='pending', max_length=30)),
                ('estimated_tokens', models.PositiveIntegerField(default=0)),
                ('actual_tokens', models.PositiveIntegerField(default=0)),
                ('requests_count', models.PositiveIntegerField(default=0)),
                ('rate_limit_headers', models.JSONField(blank=True, default=dict)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('error_code', models.CharField(blank=True, db_index=True, max_length=80)),
                ('error_message', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='api.contentgenerationrun')),
            ],
            options={
                'ordering': ['run_id', 'order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='CerebrasUsageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('model', models.CharField(blank=True, db_index=True, max_length=120)),
                ('task', models.CharField(blank=True, db_index=True, max_length=80)),
                ('endpoint', models.CharField(default='chat/completions', max_length=255)),
                ('status_code', models.IntegerField(blank=True, db_index=True, null=True)),
                ('success', models.BooleanField(db_index=True, default=False)),
                ('estimated_tokens', models.PositiveIntegerField(default=0)),
                ('actual_tokens', models.PositiveIntegerField(default=0)),
                ('charged_tokens', models.PositiveIntegerField(default=0)),
                ('response_time_ms', models.PositiveIntegerField(default=0)),
                ('rate_limit_headers', models.JSONField(blank=True, default=dict)),
                ('retry_after_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('creado_en', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cerebras_usage_logs', to='api.apikey')),
                ('listado', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cerebras_usage_logs', to='api.listado')),
                ('run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cerebras_usage_logs', to='api.contentgenerationrun')),
                ('step', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cerebras_usage_logs', to='api.contentgenerationstep')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cerebras_usage_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-creado_en', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='contentgenerationrun',
            index=models.Index(fields=['user', 'status', 'started_at'], name='api_content_user_id_042afc_idx'),
        ),
        migrations.AddIndex(
            model_name='contentgenerationrun',
            index=models.Index(fields=['listado', 'status', 'started_at'], name='api_content_listado_60561e_idx'),
        ),
        migrations.AddIndex(
            model_name='contentgenerationrun',
            index=models.Index(fields=['api_key', 'status', 'started_at'], name='api_content_api_key_729de5_idx'),
        ),
        migrations.AddIndex(
            model_name='contentgenerationstep',
            index=models.Index(fields=['run', 'step'], name='api_content_run_id_76a9ea_idx'),
        ),
        migrations.AddIndex(
            model_name='contentgenerationstep',
            index=models.Index(fields=['run', 'status'], name='api_content_run_id_d5582f_idx'),
        ),
        migrations.AddConstraint(
            model_name='contentgenerationstep',
            constraint=models.UniqueConstraint(fields=('run', 'step'), name='unique_generation_step_per_run'),
        ),
        migrations.AddIndex(
            model_name='cerebrasusagelog',
            index=models.Index(fields=['api_key', 'creado_en'], name='api_cerebra_api_key_f6398e_idx'),
        ),
        migrations.AddIndex(
            model_name='cerebrasusagelog',
            index=models.Index(fields=['user', 'creado_en'], name='api_cerebra_user_id_c37568_idx'),
        ),
        migrations.AddIndex(
            model_name='cerebrasusagelog',
            index=models.Index(fields=['listado', 'creado_en'], name='api_cerebra_listado_fba975_idx'),
        ),
        migrations.AddIndex(
            model_name='cerebrasusagelog',
            index=models.Index(fields=['run', 'creado_en'], name='api_cerebra_run_id_c942ce_idx'),
        ),
        migrations.AddIndex(
            model_name='cerebrasusagelog',
            index=models.Index(fields=['task', 'success'], name='api_cerebra_task_c6f05e_idx'),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_content_generation_plan_step'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agent',
            name='plan_nombre',
            field=models.CharField(
                choices=[
                    ('free', 'Free'),
                    ('starter', 'Starter'),
                    ('pro', 'Pro'),
                    ('scale', 'Scale'),
                    ('business', 'Business'),
                ],
                default='starter',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='accesscode',
            name='target_plan',
            field=models.CharField(
                choices=[
                    ('free', 'Free'),
                    ('starter', 'Starter'),
                    ('pro', 'Pro'),
                    ('scale', 'Scale'),
                ],
                default='starter',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='adminalert',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('quota_warning', 'Quota Warning'),
                    ('api_dead', 'API Muerta'),
                    ('pool_low', 'Pool bajo — menos de 3 disponibles'),
                    ('user_abuse', 'Abuso de usuario'),
                    ('trial_token_request', 'Token solicitado'),
                    ('voice_complaint', 'Reclamo de voz'),
                    ('high_error_rate', 'Alta tasa de errores'),
                    ('webhook_error', 'Error en Webhook'),
                    ('assign_failed', 'Fallo en asignación de APIs'),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='VideoVoiceComplaint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('complaint_only', 'Solo reclamo'), ('complaint_and_silent', 'Reclamo y video sin voz'), ('retry_voice', 'Reintentar voz')], max_length=30)),
                ('error_message', models.TextField(blank=True)),
                ('email_status', models.CharField(choices=[('pending', 'Pendiente'), ('sent', 'Enviado'), ('failed', 'Fallido'), ('console', 'Consola')], default='pending', max_length=20)),
                ('email_detail', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('listado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='voice_complaints', to='api.listado')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_voice_complaints', to='api.agent')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'created_at'], name='api_videovo_user_id_bad7b6_idx'),
                    models.Index(fields=['listado', 'created_at'], name='api_videovo_listado_337810_idx'),
                    models.Index(fields=['action', 'email_status'], name='api_videovo_action_087797_idx'),
                ],
            },
        ),
    ]

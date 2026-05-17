from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_add_last_seen_to_agent'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComercialAgentProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=255)),
                ('rol', models.CharField(blank=True, max_length=120, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('telefono_e164', models.CharField(blank=True, max_length=20, null=True)),
                ('foto_url', models.TextField(blank=True, null=True)),
                ('is_default', models.BooleanField(default=False)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commercial_agents', to='api.agent')),
            ],
            options={
                'ordering': ['-is_default', '-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='comercialagentprofile',
            index=models.Index(fields=['owner', 'is_default'], name='api_comerci_owner_i_f4f2e2_idx'),
        ),
        migrations.AddIndex(
            model_name='comercialagentprofile',
            index=models.Index(fields=['owner', 'activo'], name='api_comerci_owner_i_4d2f98_idx'),
        ),
        migrations.AddConstraint(
            model_name='comercialagentprofile',
            constraint=models.UniqueConstraint(condition=models.Q(is_default=True), fields=('owner',), name='unique_default_commercial_agent_per_owner'),
        ),
    ]

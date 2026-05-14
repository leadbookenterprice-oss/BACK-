from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_brandtemplaterevision_gemini_instructions_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CRMClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=180)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('telefono', models.CharField(blank=True, max_length=40, null=True)),
                ('estado', models.CharField(choices=[('nuevo', 'Nuevo'), ('contactado', 'Contactado'), ('interesado', 'Interesado'), ('visita', 'Visita agendada'), ('cerrado', 'Cerrado'), ('descartado', 'Descartado')], default='nuevo', max_length=24)),
                ('origen', models.CharField(blank=True, max_length=80, null=True)),
                ('presupuesto', models.CharField(blank=True, max_length=80, null=True)),
                ('ciudad_interes', models.CharField(blank=True, max_length=120, null=True)),
                ('notas', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crm_clients', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [models.Index(fields=['owner', 'estado'], name='api_crmclie_owner_i_2ce276_idx'), models.Index(fields=['owner', 'updated_at'], name='api_crmclie_owner_i_4672d5_idx')],
            },
        ),
    ]

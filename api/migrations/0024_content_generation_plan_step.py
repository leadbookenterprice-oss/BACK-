from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_internal_api_pool_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentgenerationstep',
            name='step',
            field=models.CharField(
                choices=[
                    ('plan', 'Plan'),
                    ('pdf', 'PDF'),
                    ('post', 'Post'),
                    ('story', 'Story'),
                    ('carrusel', 'Carrusel'),
                    ('email', 'Email'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]

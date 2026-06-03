from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_lead_pipelinestage_leadevent_leadassignment_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_total_bytes',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_used_bytes',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_free_bytes',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_usage_percent',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_status',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_error',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_upload_probe_ok',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='cloudinary_last_tested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

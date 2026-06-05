from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import APIKey, AdminAlert, CerebrasUsageLog, Servicio
from api.views_admin import admin_api_usage_logs, admin_api_usage_summary


class ApiUsageMonitoringTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(
            email='admin@example.com',
            password='pass12345',
            is_staff=True,
        )
        self.cerebras_service, _ = Servicio.objects.get_or_create(
            nombre='cerebras',
            defaults={
                'descripcion': 'Cerebras',
                'default_daily_limit': 1000000,
            },
        )

    def _staff_get(self, path, view):
        request = self.factory.get(path)
        force_authenticate(request, user=self.user)
        return view(request)

    def test_summary_returns_key_usage_and_creates_warning_alert(self):
        APIKey.objects.create(
            servicio=self.cerebras_service,
            api_key='ck-test-summary',
            status='available',
            google_daily_limit=1000000,
            slot_tokens_today=850000,
        )

        response = self._staff_get('/api/admin/api-usage/summary/', admin_api_usage_summary)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['keys'][0]['service'], 'cerebras')
        self.assertEqual(response.data['keys'][0]['unit'], 'tokens')
        self.assertEqual(response.data['keys'][0]['percent'], 85)
        self.assertTrue(AdminAlert.objects.filter(tipo='quota_warning', severidad='warning').exists())

    def test_logs_return_cerebras_specific_fields(self):
        key = APIKey.objects.create(
            servicio=self.cerebras_service,
            api_key='ck-test-logs',
            status='available',
            google_daily_limit=1000000,
        )
        CerebrasUsageLog.objects.create(
            api_key=key,
            user=self.user,
            model='gpt-oss-120b',
            task='post_caption',
            status_code=429,
            success=False,
            estimated_tokens=4000,
            actual_tokens=0,
            charged_tokens=4000,
            retry_after_seconds=60,
            rate_limit_headers={'x-ratelimit-remaining-tokens-minute': '0'},
            error_message='rate limited',
        )

        response = self._staff_get('/api/admin/api-usage/logs/?service=cerebras', admin_api_usage_logs)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        row = response.data['logs'][0]
        self.assertEqual(row['source'], 'cerebras')
        self.assertEqual(row['service'], 'cerebras')
        self.assertEqual(row['status_code'], 429)
        self.assertEqual(row['task'], 'post_caption')
        self.assertEqual(row['charged_tokens'], 4000)
        self.assertEqual(row['retry_after_seconds'], 60)

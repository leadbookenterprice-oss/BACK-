import os
import csv
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Agent, APIKey, Servicio, UserAPIAssignment
from api.services.pool_service import APIPoolService


class AdminSessionAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @override_settings(ALLOW_ADMIN_KEY_AUTH=False)
    def test_admin_session_login_does_not_require_real_user(self):
        with patch.dict(os.environ, {
            'ADMIN_DASH_EMAIL': 'ops@leadbook.local',
            'ADMIN_DASH_PASSWORD': 'admin-secret',
        }, clear=False):
            response = self.client.post('/api/auth/admin-login/', {
                'email': 'ops@leadbook.local',
                'password': 'admin-secret',
            }, format='json')

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.get('access'))
            self.assertTrue(response.data.get('user', {}).get('is_admin_session'))
            self.assertFalse(Agent.objects.filter(email='ops@leadbook.local').exists())

            stats = self.client.get('/api/admin/stats/', HTTP_X_ADMIN_SESSION=response.data['access'])
            self.assertEqual(stats.status_code, 200)
            self.assertIn('stats', stats.data)

    @override_settings(ALLOW_ADMIN_KEY_AUTH=False)
    def test_admin_session_login_rejects_invalid_password(self):
        with patch.dict(os.environ, {
            'ADMIN_DASH_EMAIL': 'ops@leadbook.local',
            'ADMIN_DASH_PASSWORD': 'admin-secret',
        }, clear=False):
            response = self.client.post('/api/auth/admin-login/', {
                'email': 'ops@leadbook.local',
                'password': 'wrong',
            }, format='json')

            self.assertEqual(response.status_code, 401)
            self.assertFalse(response.data.get('access'))


class AdminApiKeysExportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = Agent.objects.create_user(
            email='staff@leadbook.local',
            password='secret',
            nombre='Staff',
            is_staff=True,
        )
        self.gemini, _ = Servicio.objects.get_or_create(nombre='gemini', defaults={'activo': True})
        self.cloudinary, _ = Servicio.objects.get_or_create(nombre='cloudinary', defaults={'activo': True})

    def _read_csv(self, response):
        content = response.content.decode('utf-8-sig')
        return list(csv.DictReader(StringIO(content)))

    def test_export_requires_admin_session_or_staff_auth(self):
        response = self.client.get('/api/admin/apikeys/export/?include_secrets=1')

        self.assertEqual(response.status_code, 403)

    def test_export_returns_real_api_key_in_csv(self):
        self.client.force_authenticate(user=self.admin)
        APIKey.objects.create(
            servicio=self.gemini,
            api_key='gemini-real-secret-key',
            label='Gemini backup',
            status='available',
            google_daily_limit=1500,
        )

        response = self.client.get('/api/admin/apikeys/export/?include_secrets=1')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(response.content.startswith('\ufeff'.encode('utf-8')))
        rows = self._read_csv(response)
        gemini_row = next(row for row in rows if row['api_key'] == 'gemini-real-secret-key')
        self.assertEqual(gemini_row['service'], 'gemini')
        self.assertEqual(gemini_row['label'], 'Gemini backup')

    def test_export_includes_cloudinary_key(self):
        self.client.force_authenticate(user=self.admin)
        APIKey.objects.create(
            servicio=self.cloudinary,
            api_key='cloudinary://cloud-key:cloud-secret@leadbook-cloud',
            label='leadbook-cloud',
            status='available',
            cloudinary_status='OK',
            cloudinary_usage_percent=42.5,
        )

        response = self.client.get('/api/admin/apikeys/export/?include_secrets=1')

        self.assertEqual(response.status_code, 200)
        rows = self._read_csv(response)
        cloudinary_rows = [row for row in rows if row['service'] == 'cloudinary']
        self.assertEqual(len(cloudinary_rows), 1)
        self.assertEqual(cloudinary_rows[0]['api_key'], 'cloudinary://cloud-key:cloud-secret@leadbook-cloud')
        self.assertEqual(cloudinary_rows[0]['cloudinary_status'], 'OK')


class AdminBootstrapCleanupTests(TestCase):
    def setUp(self):
        self.gemini, _ = Servicio.objects.get_or_create(nombre='gemini', defaults={'activo': True})

    def test_staff_user_never_receives_pool_assignment(self):
        key = APIKey.objects.create(servicio=self.gemini, api_key='gemini-available', status='available')
        staff = Agent.objects.create_user(
            email='admin@leadbook.com.ar',
            password='secret',
            nombre='LeadBook Admin',
            is_staff=True,
            is_superuser=True,
        )

        self.assertFalse(UserAPIAssignment.objects.filter(user=staff).exists())
        self.assertEqual(APIPoolService.assign_keys_to_user(staff), [])
        self.assertFalse(UserAPIAssignment.objects.filter(user=staff).exists())
        key.refresh_from_db()
        self.assertEqual(key.status, 'available')

    def test_normal_user_still_receives_pool_assignment(self):
        APIKey.objects.create(servicio=self.gemini, api_key='gemini-normal', status='available')
        user = Agent.objects.create_user(
            email='cliente@leadbook.local',
            password='secret',
            nombre='Cliente',
            plan_nombre='starter',
        )

        self.assertTrue(UserAPIAssignment.objects.filter(user=user, servicio=self.gemini, activo=True).exists())

    def test_cleanup_bootstrap_admin_releases_keys_and_soft_deletes_user(self):
        key = APIKey.objects.create(servicio=self.gemini, api_key='gemini-legacy-admin', status='assigned')
        staff = Agent.objects.create_user(
            email='admin@leadbook.com.ar',
            password='secret',
            nombre='LeadBook Admin',
            is_staff=True,
            is_superuser=True,
        )
        UserAPIAssignment.objects.create(user=staff, apikey=key, servicio=self.gemini, activo=True)

        out = StringIO()
        call_command('cleanup_bootstrap_admin', stdout=out)

        self.assertFalse(Agent.objects.filter(email='admin@leadbook.com.ar').exists())
        cleaned = Agent.objects.all_including_deleted().get(id=staff.id)
        self.assertFalse(cleaned.is_active)
        self.assertFalse(cleaned.is_staff)
        self.assertFalse(cleaned.is_superuser)
        self.assertIsNotNone(cleaned.eliminado_en)
        self.assertFalse(UserAPIAssignment.objects.filter(user=cleaned, activo=True).exists())
        key.refresh_from_db()
        self.assertEqual(key.status, 'available')

import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Agent


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

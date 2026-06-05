from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import PerfilView


class ProfileLocaleSettingsTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_user(
            email='locale@example.com',
            password='pass12345',
            nombre='Locale User',
        )

    def _request(self, method='get', payload=None):
        view = PerfilView.as_view()
        request = getattr(self.factory, method)('/api/auth/perfil/', payload or {}, format='json')
        force_authenticate(request, user=self.user)
        return view(request)

    def test_get_profile_defaults_locale_to_auto(self):
        response = self._request()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['settings']['locale'], 'auto')

    def test_put_accepts_supported_locale(self):
        response = self._request('put', {'settings': {'locale': 'pt'}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['settings']['locale'], 'pt')

    def test_put_normalizes_invalid_locale_to_auto(self):
        response = self._request('put', {'settings': {'locale': 'fr'}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['settings']['locale'], 'auto')

    def test_put_normalizes_existing_invalid_locale_when_locale_is_omitted(self):
        self.user.settings = {'locale': 'fr', 'dark_mode': False}
        self.user.save(update_fields=['settings'])

        response = self._request('put', {'settings': {'dark_mode': True}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['settings']['locale'], 'auto')

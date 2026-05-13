from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from unittest.mock import patch

from api.models import AgentMediaAsset, ComercialAgentProfile


class CommercialAgentPhotoFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='agent-photo-test@leadbook.local',
            password='test-pass',
            nombre='Test Agent',
        )
        self.profile = ComercialAgentProfile.objects.create(
            owner=self.user,
            nombre='Test Comercial',
            email=self.user.email,
            telefono_e164='+5491112345678',
            is_default=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_upload_delete_agent_photo_and_content_preferences(self):
        png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
            b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        file_obj = SimpleUploadedFile('agent.png', png, content_type='image/png')
        metadata = {
            'cloud_name': 'unit-test-cloud',
            'cloudinary_account': 'unit-test-cloud',
            'public_id': 'leadbook/avatars/user_test/avatar_unit',
            'resource_type': 'image',
            'secure_url': 'https://res.cloudinary.com/unit-test-cloud/image/upload/leadbook/avatars/user_test/avatar_unit.png',
            'url': 'https://res.cloudinary.com/unit-test-cloud/image/upload/leadbook/avatars/user_test/avatar_unit.png',
            'bytes': len(png),
            'format': 'png',
            'folder': 'leadbook/avatars/user_test',
            'original_filename': 'agent',
            'version': '1',
        }

        with patch('api.views.AlmacenamientoCloudinary.guardar_avatar_metadata', return_value=metadata):
            response = self.client.post(
                reverse('commercial_agent_photo', kwargs={'agent_id': self.profile.id}),
                {'file': file_obj},
                format='multipart',
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.profile.refresh_from_db()
        asset = AgentMediaAsset.objects.get(profile=self.profile, kind='agent_photo')
        self.assertTrue(asset.is_active)
        self.assertEqual(asset.public_id, metadata['public_id'])
        self.assertEqual(asset.cloud_name, metadata['cloud_name'])
        self.assertEqual(self.profile.foto_url, metadata['secure_url'])

        with patch('api.views.cloudinary.uploader.destroy', return_value={'result': 'ok'}):
            delete_response = self.client.delete(
                reverse('commercial_agent_photo', kwargs={'agent_id': self.profile.id})
            )

        self.assertEqual(delete_response.status_code, 200, delete_response.content)
        asset.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(asset.is_active)
        self.assertEqual(self.profile.foto_url, '')

        prefs_response = self.client.get(reverse('content_preferences_detail'))
        self.assertEqual(prefs_response.status_code, 200, prefs_response.content)

        prefs_update = self.client.put(
            reverse('content_preferences_detail'),
            {'hashtags': ['venta', '#lujo'], 'emoji_density': 'high', 'use_emojis': True, 'tone': 'lujo'},
            format='json',
        )
        self.assertEqual(prefs_update.status_code, 200, prefs_update.content)
        self.assertEqual(prefs_update.json()['hashtags'], ['#venta', '#lujo'])

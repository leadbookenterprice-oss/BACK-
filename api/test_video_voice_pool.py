import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from api.ai_services import call_elevenlabs_api
from api.models import APIKey, AdminAlert, Listado, Servicio, UserAPIAssignment, VideoVoiceComplaint
from api.services.pool_service import APIPoolService


class _MockResponse:
    def __init__(self, status_code, body='', content=b''):
        self.status_code = status_code
        self.text = body
        self.content = content
        self.headers = {}

    def json(self):
        return {}


class VideoVoicePoolTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='voice-user@leadbook.local',
            password='test-pass',
            nombre='Voice User',
            plan_nombre='starter',
            plan_activo=True,
        )
        self.elevenlabs, _ = Servicio.objects.get_or_create(
            nombre='elevenlabs',
            defaults={'descripcion': 'ElevenLabs'},
        )
        self.uploadpost, _ = Servicio.objects.get_or_create(
            nombre='uploadpost',
            defaults={'descripcion': 'UploadPost'},
        )
        APIKey.objects.filter(servicio__in=[self.elevenlabs, self.uploadpost]).delete()

    @override_settings(DEBUG=False)
    @patch.dict(os.environ, {'ALLOW_GLOBAL_API_FALLBACK': 'false'}, clear=False)
    @patch('api.ai_services.requests.post')
    def test_elevenlabs_pool_falls_back_to_next_key(self, mock_post):
        first = APIKey.objects.create(servicio=self.elevenlabs, api_key='el-first', status='available')
        second = APIKey.objects.create(servicio=self.elevenlabs, api_key='el-second', status='available')
        mock_post.side_effect = [
            _MockResponse(429, '{"detail":{"status":"quota_exceeded"}}'),
            _MockResponse(200, content=b'audio-bytes'),
        ]

        audio = call_elevenlabs_api('Hola mundo', agente=self.user, voz='femenina')

        self.assertEqual(audio, b'audio-bytes')
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, 'exhausted')
        self.assertGreaterEqual(first.error_count, 1)
        self.assertEqual(second.total_requests, 1)
        self.assertEqual(mock_post.call_count, 2)

    def test_free_user_does_not_receive_uploadpost_assignment(self):
        APIKey.objects.create(servicio=self.uploadpost, api_key='up-free-test', status='available')
        self.user.plan_nombre = 'free'
        self.user.save(update_fields=['plan_nombre'])

        assignment = APIPoolService.ensure_uploadpost_assignment(self.user)

        self.assertIsNone(assignment)
        self.assertFalse(UserAPIAssignment.objects.filter(user=self.user, servicio=self.uploadpost, activo=True).exists())

    def test_paid_user_receives_uploadpost_assignment(self):
        key = APIKey.objects.create(servicio=self.uploadpost, api_key='up-paid-test', status='available')

        assignment = APIPoolService.ensure_uploadpost_assignment(self.user)

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.apikey_id, key.id)
        key.refresh_from_db()
        self.assertEqual(key.status, 'assigned')

    def test_voice_complaint_is_saved_and_alerted(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa con voz fallida',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cairo',
            precio='1500000',
            moneda='USD',
            video_status='voice_failed',
            datos_extra={
                'video_voice_status': 'failed',
                'video_voice_error': 'ElevenLabs quota',
                'video_voice_requires_decision': True,
            },
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            reverse('video_voice_complaint', args=[listado.id]),
            {'action': 'complaint_only'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(VideoVoiceComplaint.objects.filter(listado=listado, user=self.user).count(), 1)
        self.assertTrue(AdminAlert.objects.filter(tipo='voice_complaint', related_user=self.user).exists())
        listado.refresh_from_db()
        self.assertEqual(listado.video_status, 'voice_failed')

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import Listado, UsageLog


class VideoStudioQuickBaseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='video-studio@leadbook.local',
            password='test-pass',
            nombre='Video Studio User',
            plan_nombre='starter',
            plan_activo=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_creates_video_only_listing_without_property_usage(self):
        response = self.client.post(reverse('video_studio_quick_base'), {
            'tipoPropiedad': 'Departamento',
            'operacion': 'venta',
            'moneda': 'USD',
            'precio': '250000',
            'ciudad': 'Miami',
            'tipoVideo': 'reel',
            'voz': 'femenina',
            'tono': 'profesional',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        listado = Listado.objects.get(id=response.data['listado']['id'])
        self.assertTrue(listado.datos_extra['video_only'])
        self.assertEqual(listado.datos_extra['source'], 'video_studio_quick')
        self.assertEqual(listado.video_status, 'script_pending')
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 0)

    def test_listados_hide_video_only_by_default_and_include_when_requested(self):
        normal = Listado.objects.create(
            agente=self.user,
            titulo='Casa normal',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cairo',
            precio='100000',
            moneda='USD',
            datos_extra={'tipoPropiedad': 'Casa'},
        )
        quick = Listado.objects.create(
            agente=self.user,
            titulo='Video rapido',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cairo',
            precio='100000',
            moneda='USD',
            video_status='script_pending',
            datos_extra={'video_only': True, 'source': 'video_studio_quick'},
        )

        default_response = self.client.get(reverse('listados'))
        self.assertEqual(default_response.status_code, 200)
        self.assertEqual([item['id'] for item in default_response.data], [normal.id])

        include_response = self.client.get(reverse('listados'), {'include_video_only': '1'})
        self.assertEqual(include_response.status_code, 200)
        self.assertCountEqual([item['id'] for item in include_response.data], [normal.id, quick.id])

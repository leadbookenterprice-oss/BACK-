import json
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from api.ai_services import APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError
from api.models import APIKey, AgentMediaAsset, ComercialAgentProfile, ConfiguracionSistema, ContentGenerationRun, Listado, Notificacion, OTPCode, Servicio, UsageLog, UserAPIAssignment
from api.pool_manager import get_next_available_api
from api.services.ai_router import build_ai_root_payload
from api.services.ai_limits import get_model_limit_config, load_ai_limits_config
from api.services.cerebras_generation_protocol import PROTOCOL_VERSION, create_generation_protocol
from api.services.content_generation import CONTENT_PACK_STEPS, start_or_resume_generation_run
from api.services.nvidia_models import NVIDIA_FREE_MODELS_CONFIG_KEY, discover_nvidia_free_models, normalize_nvidia_models


class _FakeStreamResponse:
    status_code = 200
    headers = {'content-type': 'application/pdf'}

    def __init__(self, content):
        self.content = content

    def iter_content(self, chunk_size=8192):
        yield self.content


class _FakeTurnstileResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class GeminiPoolSelectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='gemini-pool-test@leadbook.local',
            password='test-pass',
            nombre='Gemini Pool Tester',
            plan_nombre='starter',
        )
        self.service, _ = Servicio.objects.update_or_create(
            nombre='gemini',
            defaults={
                'descripcion': 'Google Gemini',
                'default_daily_limit': 1500,
            },
        )
        APIKey.objects.filter(servicio=self.service).delete()

    def _create_key(self, api_key, status='available', requests_today=0):
        return APIKey.objects.create(
            servicio=self.service,
            api_key=api_key,
            status=status,
            requests_today=requests_today,
            google_daily_limit=1500,
        )

    def test_get_next_available_api_never_reuses_exhausted_key(self):
        self._create_key('AIza-exhausted', status='exhausted')

        selected = get_next_available_api(self.user, 'gemini')

        self.assertIsNone(selected)

    def test_get_next_available_api_uses_available_pool_key_without_assignment(self):
        self._create_key('AIza-exhausted', status='exhausted')
        replacement_key = self._create_key('AIza-replacement', status='available')

        selected = get_next_available_api(self.user, 'gemini')

        self.assertEqual(selected, 'AIza-replacement')
        replacement_key.refresh_from_db()
        self.assertEqual(replacement_key.status, 'available')


class UploadPostAssignmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='uploadpost-user-one@leadbook.local',
            password='test-pass',
            nombre='UploadPost User One',
            plan_nombre='starter',
        )
        self.other_user = get_user_model().objects.create_user(
            email='uploadpost-user-two@leadbook.local',
            password='test-pass',
            nombre='UploadPost User Two',
            plan_nombre='starter',
        )
        self.service, _ = Servicio.objects.update_or_create(
            nombre='uploadpost',
            defaults={
                'descripcion': 'UploadPost',
                'default_daily_limit': 999999,
                'default_monthly_limit': 10,
            },
        )
        APIKey.objects.filter(servicio=self.service).delete()

    def _create_key(self, api_key, status='available', requests_this_month=0):
        return APIKey.objects.create(
            servicio=self.service,
            api_key=api_key,
            status=status,
            requests_this_month=requests_this_month,
            google_daily_limit=999999,
            google_monthly_limit=10,
        )

    def test_uploadpost_assigns_one_key_per_user_and_reuses_it(self):
        first_key = self._create_key('uploadpost-user-one-key')
        self._create_key('uploadpost-spare-key')

        selected = get_next_available_api(self.user, 'uploadpost')
        selected_again = get_next_available_api(self.user, 'uploadpost')

        self.assertEqual(selected, first_key.api_key)
        self.assertEqual(selected_again, first_key.api_key)
        first_key.refresh_from_db()
        self.assertEqual(first_key.status, 'assigned')
        self.assertEqual(
            UserAPIAssignment.objects.filter(
                user=self.user,
                servicio=self.service,
                activo=True,
            ).count(),
            1,
        )

    def test_uploadpost_second_user_gets_different_key(self):
        first_key = self._create_key('uploadpost-user-one-key')
        second_key = self._create_key('uploadpost-user-two-key')

        selected = get_next_available_api(self.user, 'uploadpost')
        selected_other = get_next_available_api(self.other_user, 'uploadpost')

        self.assertEqual(selected, first_key.api_key)
        self.assertEqual(selected_other, second_key.api_key)
        self.assertEqual(
            set(UserAPIAssignment.objects.filter(activo=True).values_list('apikey__api_key', flat=True)),
            {first_key.api_key, second_key.api_key},
        )


class AdminAPIKeyPoolDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            email='admin-delete-key@leadbook.local',
            password='test-pass',
            nombre='Admin Delete Key',
            is_staff=True,
        )
        self.user = get_user_model().objects.create_user(
            email='assigned-key-user@leadbook.local',
            password='test-pass',
            nombre='Assigned Key User',
            plan_nombre='starter',
        )
        self.service, _ = Servicio.objects.update_or_create(
            nombre='cerebras',
            defaults={
                'descripcion': 'Cerebras',
                'default_daily_limit': 1000000,
            },
        )
        self.client.force_authenticate(self.admin)

    def test_admin_can_delete_key_with_historical_assignment(self):
        key = APIKey.objects.create(
            servicio=self.service,
            api_key='csk-protected-delete-test',
            label='Cerebras protected delete test',
            status='exhausted',
            google_daily_limit=1000000,
        )
        UserAPIAssignment.objects.create(
            user=self.user,
            apikey=key,
            servicio=self.service,
            is_primary=True,
            activo=False,
        )

        response = self.client.delete(f'/api/admin/apikeys/pool/{key.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(APIKey.objects.filter(id=key.id).exists())
        self.assertFalse(UserAPIAssignment.objects.filter(apikey_id=key.id).exists())


class NvidiaModelDiscoveryTests(TestCase):
    def setUp(self):
        self.service, _ = Servicio.objects.update_or_create(
            nombre='nvidia',
            defaults={
                'descripcion': 'NVIDIA NIM',
                'default_daily_limit': 1500,
            },
        )
        APIKey.objects.filter(servicio=self.service).delete()

    def test_normalize_nvidia_models_keeps_free_or_accessible_models(self):
        payload = {
            'data': [
                {'id': 'meta/llama-3.1-70b-instruct'},
                {'id': 'nvidia/paid-model', 'free_endpoint': False},
                {'id': 'nvidia/free-model', 'freeEndpoint': True, 'display_name': 'Free Model'},
                {'id': 'meta/llama-3.1-70b-instruct'},
            ],
        }

        models = normalize_nvidia_models(payload)

        self.assertEqual(
            [item['model'] for item in models],
            ['meta/llama-3.1-70b-instruct', 'nvidia/free-model'],
        )
        self.assertEqual(models[1]['label'], 'Free Model')

    @patch('api.services.nvidia_models.requests.get')
    def test_discover_nvidia_free_models_persists_catalog(self, mock_get):
        APIKey.objects.create(
            servicio=self.service,
            api_key='nvapi-test',
            status='available',
        )

        class FakeResponse:
            status_code = 200
            content = b'{}'

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {'id': 'meta/llama-3.1-70b-instruct'},
                        {'id': 'deepseek-ai/deepseek-v4-flash', 'free_endpoint': True},
                    ],
                }

        mock_get.return_value = FakeResponse()

        payload = discover_nvidia_free_models(requested_by='test')

        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['count'], 2)
        cfg = ConfiguracionSistema.objects.get(clave=NVIDIA_FREE_MODELS_CONFIG_KEY)
        self.assertEqual(cfg.valor, '2')
        self.assertEqual(cfg.datos['models'][0]['model'], 'deepseek-ai/deepseek-v4-flash')
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs['headers']['Authorization'], 'Bearer nvapi-test')

    def test_ai_root_payload_uses_cached_nvidia_models(self):
        APIKey.objects.create(
            servicio=self.service,
            api_key='nvapi-test',
            status='available',
        )
        ConfiguracionSistema.objects.update_or_create(
            clave=NVIDIA_FREE_MODELS_CONFIG_KEY,
            defaults={
                'valor': '1',
                'datos': {
                    'provider': 'nvidia',
                    'status': 'ok',
                    'models': [
                        {'model': 'nvidia/nemotron-demo', 'label': 'Nemotron Demo'},
                    ],
                },
            },
        )

        payload = build_ai_root_payload()
        nvidia = next(item for item in payload['providers'] if item['provider'] == 'nvidia')

        self.assertEqual(nvidia['models_source'], 'discovered')
        self.assertEqual(nvidia['models'][0]['model'], 'nvidia/nemotron-demo')
        self.assertTrue(nvidia['models'][0]['selectable'])


class AILimitsAndProtocolTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='protocol-user@leadbook.local',
            password='test-pass',
            nombre='Protocol User',
            plan_nombre='starter',
            plan_activo=True,
        )
        self.listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa luminosa',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cordoba',
            barrio='Centro',
            precio='250000',
            moneda='USD',
            metros_cuadrados=180,
            datos_extra={
                'amenidades': ['Pileta', 'Quincho'],
                'descripcion': 'Casa amplia con jardin y buena luz natural.',
                'template_id': 'arena_clara',
            },
        )

    def test_ai_limits_config_loads_cerebras_free_models(self):
        config = load_ai_limits_config()
        glm = get_model_limit_config('cerebras', 'zai-glm-4.7')
        gpt = get_model_limit_config('cerebras', 'gpt-oss-120b')

        self.assertEqual(config['version'], 1)
        self.assertEqual(glm['limits']['requests_per_minute'], 5)
        self.assertEqual(gpt['limits']['tokens_per_day'], 1000000)

    def test_generation_run_starts_with_plan_step(self):
        run, reservation = start_or_resume_generation_run(
            self.user,
            self.listado,
            metadata={'ai_provider': 'gemini'},
        )

        self.assertIsNone(reservation['error'])
        self.assertEqual(run.current_step, 'plan')
        self.assertEqual(
            list(run.steps.order_by('order').values_list('step', flat=True)),
            CONTENT_PACK_STEPS,
        )

    @patch('api.ai_services.call_cerebras_api')
    def test_cerebras_protocol_is_ai_generated_and_normalized(self, mock_call):
        mock_call.return_value = json.dumps({
            'version': PROTOCOL_VERSION,
            'creative_direction': {
                'tone': 'premium concreto',
                'positioning': 'familia e inversion',
                'main_angle': 'luz y jardin',
                'avoid': ['datos inventados'],
            },
            'asset_instructions': {
                'pdf': 'Priorizar jardin y galeria.',
                'post': 'Caption aspiracional concreto.',
                'story': 'CTA breve.',
                'carrusel': 'Narrativa por recorrido.',
                'email': 'Correo profesional.',
            },
            'requested_outputs': ['pdf', 'post', 'story', 'carrusel', 'email'],
        })
        run = ContentGenerationRun.objects.create(
            user=self.user,
            listado=self.listado,
            status='running',
            current_step='plan',
            metadata={'ai_provider': 'cerebras', 'selected_template': 'arena_clara'},
        )

        protocol = create_generation_protocol(run, payload={'template_id': 'arena_clara'}, user=self.user)

        self.assertEqual(protocol['version'], PROTOCOL_VERSION)
        self.assertEqual(protocol['planner']['status'], 'ai_generated')
        self.assertEqual(protocol['planner']['primary_model'], 'zai-glm-4.7')
        self.assertEqual(protocol['planner']['fallback_model'], 'gpt-oss-120b')
        self.assertEqual(protocol['template']['id'], 'arena_clara')
        self.assertEqual(protocol['asset_instructions']['pdf'], 'Priorizar jardin y galeria.')
        mock_call.assert_called_once()


class DashboardMetricsDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='dashboard-metrics@leadbook.local',
            password='test-pass',
            nombre='Dashboard Metrics',
            plan_nombre='starter',
            plan_activo=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _aware(self, year, month, day, hour=10):
        return timezone.make_aware(datetime(year, month, day, hour, 0, 0))

    def _usage(self, tipo, fecha):
        log = UsageLog.objects.create(agent=self.user, tipo=tipo)
        UsageLog.objects.filter(pk=log.pk).update(fecha=fecha)
        return log

    def test_dashboard_metrics_detail_counts_week_month_and_legacy_fields(self):
        fixed_now = self._aware(2026, 6, 9, 12)
        self._usage('property', self._aware(2026, 6, 1))
        self._usage('property', self._aware(2026, 6, 8))
        self._usage('property', self._aware(2026, 6, 9, 9))
        self._usage('property', self._aware(2026, 6, 9, 15))
        self._usage('property', self._aware(2026, 5, 31))
        self._usage('video', self._aware(2026, 6, 8))
        self._usage('video', self._aware(2026, 6, 9))
        self._usage('video', self._aware(2026, 5, 31))
        Listado.objects.create(
            agente=self.user,
            titulo='Casa demo',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cairo',
            precio='150000',
            moneda='USD',
            videos_creados=5,
        )

        with patch('api.views.timezone.now', return_value=fixed_now):
            response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['listados_este_mes'], 4)
        self.assertEqual(payload['total_generados'], 5)
        self.assertEqual(payload['listados_guardados_total'], 1)
        self.assertEqual(payload['listados_generados_este_mes'], 4)
        self.assertEqual(payload['total_listados_generados'], 5)
        self.assertEqual(payload['videos_creados'], 2)
        self.assertIn('daily_listing_quota', payload)
        self.assertFalse(payload['listados_recientes'][0]['content_pack_ready'])
        self.assertFalse(payload['listados_recientes'][0]['counted_as_listing'])

        detail = payload['metrics_detail']
        self.assertEqual(detail['period']['today'], '2026-06-09')
        self.assertEqual(detail['period']['week_start'], '2026-06-08')
        self.assertEqual(detail['period']['week_end'], '2026-06-14')
        self.assertEqual(detail['listings']['today'], 2)
        self.assertEqual(detail['listings']['this_week'], 3)
        self.assertEqual(detail['listings']['this_month'], 4)
        self.assertEqual(detail['listings']['total'], 5)
        self.assertEqual([item['count'] for item in detail['listings']['week_days']], [1, 2, 0, 0, 0, 0, 0])
        self.assertEqual(detail['videos']['today'], 1)
        self.assertEqual(detail['videos']['this_week'], 2)
        self.assertEqual(detail['videos']['this_month'], 2)
        self.assertEqual(detail['videos']['total'], 5)
        self.assertEqual([item['count'] for item in detail['videos']['week_days']], [1, 1, 0, 0, 0, 0, 0])
        self.assertIn('listados_recientes', payload)

    def test_dashboard_metrics_detail_returns_zeroes_without_activity(self):
        fixed_now = self._aware(2026, 6, 9, 12)

        with patch('api.views.timezone.now', return_value=fixed_now):
            response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        detail = response.json()['metrics_detail']
        self.assertEqual(detail['listings']['today'], 0)
        self.assertEqual(detail['listings']['this_week'], 0)
        self.assertEqual(detail['listings']['this_month'], 0)
        self.assertEqual(detail['listings']['total'], 0)
        self.assertEqual(len(detail['listings']['week_days']), 7)
        self.assertTrue(all(item['count'] == 0 for item in detail['listings']['week_days']))
        self.assertEqual(detail['videos']['this_month'], 0)
        self.assertEqual(len(detail['videos']['week_days']), 7)


class AdsStudioEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='ads-studio-test@leadbook.local',
            password='test-pass',
            nombre='Ads Tester',
            plan_nombre='pro',
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_generate_meta_variants_persists_on_listing(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa Palermo',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={'titulo': 'Casa Palermo', 'descripcion': 'Casa premium con patio'},
        )
        ai_json = '''{"variants":[{"primary_text":"Una casa lista para mudarte en Palermo, con patio y detalles premium.","headline":"Casa premium en Palermo","description":"Agenda una visita privada.","cta":"Enviar mensaje","hook":"Patio y ubicacion","segmento_sugerido":"Familias buscando upgrade"}]}'''
        with patch('api.views.smart_call', return_value=ai_json):
            response = self.client.post(
                reverse('generate_meta_variants'),
                {'listado_id': listado.id, 'cantidad_variantes': 1, 'objetivo': 'leads'},
                format='json',
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()['variants']), 1)
        listado.refresh_from_db()
        self.assertIn('meta_variants', listado.datos_extra['resultados'])

    def test_generate_meta_variants_soft_rate_limit(self):
        with patch('api.views.smart_call', side_effect=GeminiRateLimitedError()):
            response = self.client.post(
                reverse('generate_meta_variants'),
                {'data': {'titulo': 'Casa'}, 'cantidad_variantes': 1},
                format='json',
            )
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(response.json()['quota_state'], 'soft_rate_limited')
        self.assertEqual(response.json()['error'], 'ia_rate_limited')
        self.assertFalse(Notificacion.objects.filter(usuario=self.user, tipo='quota_agotada').exists())

    def test_generate_meta_variants_hard_quota(self):
        with patch('api.views.smart_call', side_effect=GeminiQuotaExhaustedError()):
            response = self.client.post(
                reverse('generate_meta_variants'),
                {'data': {'titulo': 'Casa'}, 'cantidad_variantes': 1},
                format='json',
            )
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(response.json()['quota_state'], 'hard_exhausted')
        self.assertEqual(response.json()['error'], 'cuota_ia_agotada')
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, tipo='quota_agotada').count(), 1)

    def test_generate_meta_variants_api_key_hard_quota_notifies_once(self):
        from api.views import _quota_error_response

        for _ in range(2):
            response = _quota_error_response(
                APIKeyUnavailableError(),
                user=self.user,
                source='test_api_key_hard_quota',
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data['quota_state'], 'hard_exhausted')
        self.assertEqual(Notificacion.objects.filter(usuario=self.user, tipo='quota_agotada').count(), 1)


class ListingResultPersistenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='listing-cache-test@leadbook.local',
            password='test-pass',
            nombre='Cache Tester',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_creating_listing_registers_property_usage_immediately(self):
        response = self.client.post(
            reverse('listados'),
            {
                'formData': {
                    'titulo': 'Casa con conteo',
                    'tipoPropiedad': 'Casa',
                    'operacion': 'venta',
                    'ciudad': 'Palermo',
                    'precio': '250000',
                    'moneda': 'USD',
                }
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 1)
        quota = response.json()['daily_listing_quota']
        self.assertEqual(quota['used'], 1)
        self.assertEqual(quota['remaining'], 29)

    def test_property_usage_counts_once_after_full_content_pack_is_persisted(self):
        from api.views import actualizar_resultados_listado

        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa pack completo',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={'resultados': {}},
        )

        actualizar_resultados_listado(listado, 'pdf', {'url': 'https://res.cloudinary.com/demo/raw/upload/ficha.pdf'})
        actualizar_resultados_listado(listado, 'post', {'url': 'https://res.cloudinary.com/demo/image/upload/post.jpg'})
        actualizar_resultados_listado(listado, 'story', {'url': 'https://res.cloudinary.com/demo/image/upload/story.jpg'})
        actualizar_resultados_listado(listado, 'carrusel', {'slides': ['https://res.cloudinary.com/demo/image/upload/slide.jpg']})
        stale_listado = Listado.objects.get(pk=listado.pk)
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 0)

        actualizar_resultados_listado(listado, 'email', {'html': '<p>Mail listo</p>'})
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 1)

        listado.refresh_from_db()
        self.assertIn('property_usage_counted_at', listado.datos_extra)

        actualizar_resultados_listado(stale_listado, 'email', {'html': '<p>Mail regenerado</p>'})
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 1)

    def test_upload_fotos_replace_returns_only_current_batch(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa con fotos',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={},
        )

        def fake_upload(file_obj, user_id, listado_id=None, tipo_foto='portada', indice=0):
            stem = file_obj.name.rsplit('.', 1)[0]
            public_id = f'leadbook/listados/usuario_{user_id}/listado_{listado_id}/foto_{stem}_{tipo_foto}_{indice}'
            return {
                'public_id': public_id,
                'secure_url': f'https://res.cloudinary.com/demo/image/upload/{public_id}.webp',
                'url': f'https://res.cloudinary.com/demo/image/upload/{public_id}.webp',
                'resource_type': 'image',
                'cloudinary_account': 'demo',
                'format': 'webp',
                'width': 1200,
                'height': 900,
                'bytes': 128,
            }

        def photo(name):
            return SimpleUploadedFile(name, b'image-bytes', content_type='image/webp')

        with patch('api.services.almacenamiento.AlmacenamientoCloudinary.guardar_foto_propiedad_file', side_effect=fake_upload), \
             patch('api.views.cloudinary.uploader.destroy') as destroy_mock:
            first_response = self.client.post(
                reverse('upload_fotos_listado'),
                {
                    'mode': 'replace',
                    'delete_removed': 'true',
                    'listado_id': str(listado.id),
                    'portada_file': photo('batch1-cover.webp'),
                    'fotos_files': [photo(f'batch1-gallery-{idx}.webp') for idx in range(7)],
                },
                format='multipart',
            )
            self.assertEqual(first_response.status_code, 200, first_response.content)
            first_payload = first_response.json()
            self.assertEqual(len(first_payload['fotosRecorrido']), 7)

            removed_refs = [first_payload['portadaUrl'], *first_payload['fotosRecorrido']]
            second_response = self.client.post(
                reverse('upload_fotos_listado'),
                {
                    'mode': 'replace',
                    'delete_removed': 'true',
                    'listado_id': str(listado.id),
                    'removedMediaRefs': [json.dumps(item) for item in removed_refs],
                    'portada_file': photo('batch2-cover.webp'),
                    'fotos_files': [photo(f'batch2-gallery-{idx}.webp') for idx in range(7)],
                },
                format='multipart',
            )

        self.assertEqual(second_response.status_code, 200, second_response.content)
        second_payload = second_response.json()
        self.assertEqual(len(second_payload['fotosRecorrido']), 7)
        all_refs = [second_payload['portadaUrl'], *second_payload['fotosRecorrido']]
        self.assertTrue(all('batch2' in ref['public_id'] for ref in all_refs))
        self.assertFalse(any('batch1' in ref['public_id'] for ref in all_refs))
        self.assertEqual(destroy_mock.call_count, 8)

        listado.refresh_from_db()
        self.assertEqual(len(listado.datos_extra['fotosRecorrido']), 7)
        self.assertTrue(all('batch2' in ref['public_id'] for ref in listado.datos_extra['fotosRecorrido']))

    def test_upload_fotos_delete_removed_only_safe_user_photo_assets(self):
        safe_public_id = f'leadbook/listados/usuario_{self.user.id}/temp/foto_old_galeria_0'
        unsafe_other_user = 'leadbook/listados/usuario_999/temp/foto_other_user'
        unsafe_generated = f'leadbook/listados/usuario_{self.user.id}/temp/generated_asset_1'
        unsafe_other_folder = f'leadbook/posts/usuario_{self.user.id}/foto_post_1'

        removed_refs = [
            {'public_id': safe_public_id, 'resource_type': 'image'},
            {'public_id': unsafe_other_user, 'resource_type': 'image'},
            {'public_id': unsafe_generated, 'resource_type': 'image'},
            {'public_id': unsafe_other_folder, 'resource_type': 'image'},
        ]

        with patch('api.views.cloudinary.uploader.destroy') as destroy_mock:
            response = self.client.post(
                reverse('upload_fotos_listado'),
                {
                    'mode': 'replace',
                    'delete_removed': True,
                    'removedMediaRefs': removed_refs,
                },
                format='json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        destroy_mock.assert_called_once_with(safe_public_id, resource_type='image')

    def test_upload_fotos_rejects_unallowed_remote_urls(self):
        response = self.client.post(
            reverse('upload_fotos_listado'),
            {
                'mode': 'replace',
                'portadaUrl': {'url': 'https://cdn.example.com/cover.webp'},
                'fotosRecorrido': ['https://cdn.example.com/gallery.webp'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()['error'], 'invalid_media_payload')
        self.assertIn('URL de imagen no permitida', response.json()['mensaje'])

    def test_update_preserves_existing_generated_results(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa guardada',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={
                'titulo': 'Casa guardada',
                'resultados': {
                    'post': {'url': 'https://res.cloudinary.com/demo/image/upload/post.jpg'},
                    'carrusel': {'slides': ['https://res.cloudinary.com/demo/image/upload/slide1.jpg']},
                },
            },
        )

        response = self.client.put(
            reverse('listado_detalle', kwargs={'pk': listado.id}),
            {'datos': {'titulo': 'Casa editada', 'resultados': {'email': {'html': '<p>Mail</p>'}}}},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        listado.refresh_from_db()
        resultados = listado.datos_extra['resultados']
        self.assertEqual(resultados['post']['url'], 'https://res.cloudinary.com/demo/image/upload/post.jpg')
        self.assertEqual(resultados['carrusel']['slides'][0], 'https://res.cloudinary.com/demo/image/upload/slide1.jpg')
        self.assertEqual(resultados['email']['html'], '<p>Mail</p>')

        detail = self.client.get(reverse('listado_detalle', kwargs={'pk': listado.id}))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIn('post', detail.json()['formatos_generados'])
        self.assertIn('carrusel', detail.json()['formatos_generados'])
        self.assertIn('email', detail.json()['formatos_generados'])

    def test_descargar_pdf_streams_saved_cloudinary_url_first(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa con PDF',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={
                'resultados': {
                    'pdf': {'url': 'https://res.cloudinary.com/demo/raw/upload/ficha.pdf'}
                }
            },
        )

        with patch('api.views._is_safe_remote_asset_url', return_value=True), \
             patch('api.views.requests.get', return_value=_FakeStreamResponse(b'%PDF-1.4')):
            response = self.client.get(reverse('descargar_pdf', kwargs={'listado_id': listado.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_descargar_pdf_fallbacks_to_html_when_url_absent(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa con HTML PDF',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={
                'resultados': {
                    'pdf': {'html': '<html><body><h1>Ficha</h1></body></html>'}
                }
            },
        )

        with patch('api.services.render_engine.render_html_to_pdf', return_value=b'%PDF-1.4 HTML'):
            response = self.client.get(reverse('descargar_pdf', kwargs={'listado_id': listado.id}))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.content, b'%PDF-1.4 HTML')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_pdf_proxy_fallbacks_to_html_when_url_absent(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa con HTML PDF proxy',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={
                'resultados': {
                    'pdf': {'html': '<html><body><h1>Ficha proxy</h1></body></html>'}
                }
            },
        )

        with patch('api.services.render_engine.render_html_to_pdf', return_value=b'%PDF-1.4 PROXY'):
            response = self.client.get(reverse('pdf_proxy', kwargs={'listado_id': listado.id}))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.content, b'%PDF-1.4 PROXY')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline;', response['Content-Disposition'])

    def test_generar_pdf_uses_local_fallback_when_ai_returns_incomplete_html(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa fallback PDF',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Cairo',
            precio='1500000',
            moneda='USD',
            datos_extra={},
        )

        foto_url = 'https://res.cloudinary.com/demo/image/upload/listado/foto_1.jpg'
        payload = {
            'listado_id': listado.id,
            'template_id': 'arena_clara',
            'tipoPropiedad': 'Casa',
            'operacion': 'venta',
            'ciudad': 'Cairo',
            'precio': '1500000',
            'moneda': 'USD',
            'descripcion': 'Casa luminosa con vista panoramica y excelente distribucion.',
            'amenidades': ['Terraza', 'Vista abierta'],
            'portadaUrl': foto_url,
            'fotosRecorrido': [foto_url],
        }

        with patch('api.ai_services.generar_html_gemini', return_value='<section>PDF sin documento completo</section>'), \
             patch('api.services.render_engine.render_html_to_pdf', return_value=b'%PDF-1.4 FALLBACK'), \
             patch('api.services.almacenamiento.AlmacenamientoCloudinary.guardar_pdf', return_value='https://res.cloudinary.com/demo/raw/upload/ficha.pdf'), \
             patch('api.views._render_and_store_pdf_cover', return_value='https://res.cloudinary.com/demo/image/upload/cover.jpg'):
            response = self.client.post(reverse('generar_pdf'), payload, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['generation_source'], 'fallback_local')
        self.assertIn('html_document_missing', data['fallback_reason'])
        self.assertIn('data-leadbook-pdf="true"', data['html'])
        self.assertIn('data-template-id="arena_clara"', data['html'])

        listado.refresh_from_db()
        pdf_data = listado.datos_extra['resultados']['pdf']
        self.assertEqual(pdf_data['generation_source'], 'fallback_local')
        self.assertEqual(pdf_data['url'], 'https://res.cloudinary.com/demo/raw/upload/ficha.pdf')
        self.assertIn('data-section="gallery"', pdf_data['html'])

    def test_descargar_pdf_returns_404_without_url_or_html(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa sin PDF',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={'resultados': {'pdf': {}}},
        )

        response = self.client.get(reverse('descargar_pdf', kwargs={'listado_id': listado.id}))
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json().get('error'), 'No hay PDF generado todavía')

    def test_descargar_pdf_rejects_non_allowed_host(self):
        listado = Listado.objects.create(
            agente=self.user,
            titulo='Casa URL no permitida',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
            datos_extra={
                'resultados': {
                    'pdf': {'url': 'https://example.com/no-permitido.pdf'}
                }
            },
        )

        with patch('api.views._is_safe_remote_asset_url', return_value=False):
            response = self.client.get(reverse('descargar_pdf', kwargs={'listado_id': listado.id}))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'URL de PDF no permitida')


class CaptionEncodingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='caption-encoding-test@leadbook.local',
            password='test-pass',
            nombre='Caption Encoding Tester',
        )

    def _sample_data(self):
        return {
            'tipoPropiedad': 'Cochera',
            'ciudad': 'Dubai',
            'pais': 'Emiratos Arabes Unidos',
            'operacion': 'venta',
            'moneda': 'USD',
            'precio': '1000000',
        }

    def assertCleanSpanishCaption(self, caption):
        for marker in ('\u00c3', '\u00c2', '\u00e2\u20ac'):
            self.assertNotIn(marker, caption)
        for expected in (
            'ubicaci\u00f3n',
            'proyecci\u00f3n',
            'Adem\u00e1s',
            't\u00e9cnica',
        ):
            self.assertIn(expected, caption)

    def test_finalize_caption_repairs_fallback_extension_blocks(self):
        from api.views import _finalize_caption_text

        caption = _finalize_caption_text(
            'Oportunidad premium.',
            self._sample_data(),
            formato='post',
            prefs=None,
            max_chars=2200,
        )

        self.assertCleanSpanishCaption(caption)

    def test_actualizar_resultados_listado_persists_clean_caption(self):
        from api.views import _finalize_caption_text, actualizar_resultados_listado

        listado = Listado.objects.create(
            agente=self.user,
            titulo='Cochera Dubai',
            tipo_propiedad='cochera',
            operacion='venta',
            ciudad='Dubai',
            precio='1000000',
            moneda='USD',
            datos_extra={'resultados': {}},
        )
        caption = _finalize_caption_text(
            'Oportunidad premium.',
            self._sample_data(),
            formato='post',
            prefs=None,
            max_chars=2200,
        )

        actualizar_resultados_listado(
            listado,
            'post',
            {
                'url': 'https://res.cloudinary.com/demo/image/upload/post.jpg',
                'caption': caption,
            },
        )

        listado.refresh_from_db()
        stored_caption = listado.datos_extra['resultados']['post']['caption']
        self.assertCleanSpanishCaption(stored_caption)


class CommercialAgentPhotoFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='agent-photo-test@leadbook.local',
            password='test-pass',
            nombre='Test Agent',
            plan_nombre='pro',
            plan_activo=True,
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


class PasswordRecoveryCodeTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email='password-code-test@leadbook.local',
            password='OldPass123!',
            nombre='Password Code Tester',
        )
        self.client = APIClient()

    @override_settings(TURNSTILE_REQUIRED=True, TURNSTILE_SECRET_KEY='test-secret')
    def test_send_otp_requires_turnstile_when_enabled(self):
        response = self.client.post(
            '/api/auth/send-otp/',
            {'email': 'new-user@leadbook.local'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'turnstile_required')

    @override_settings(TURNSTILE_REQUIRED=True, TURNSTILE_SECRET_KEY='test-secret')
    def test_register_requires_turnstile_when_enabled(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'email': 'new-user@leadbook.local',
                'password': 'NewPass123!',
                'nombre': 'New User',
                'signup_type': 'paid',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'turnstile_required')

    @override_settings(TURNSTILE_REQUIRED=True, TURNSTILE_SECRET_KEY='test-secret')
    @patch('api.services.turnstile.requests.post', return_value=_FakeTurnstileResponse({'success': True}))
    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_public_recovery_accepts_valid_turnstile(self, send_otp, siteverify):
        response = self.client.post(
            '/api/auth/recuperar-password/',
            {'email': self.user.email, 'turnstile_token': 'valid-token'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(send_otp.called)
        self.assertTrue(siteverify.called)

    @override_settings(TURNSTILE_REQUIRED=True, TURNSTILE_SECRET_KEY='test-secret')
    @patch('api.services.turnstile.requests.post', return_value=_FakeTurnstileResponse({'success': False, 'error-codes': ['invalid-input-response']}))
    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_public_recovery_rejects_invalid_turnstile(self, send_otp, siteverify):
        response = self.client.post(
            '/api/auth/recuperar-password/',
            {'email': self.user.email, 'turnstile_token': 'bad-token'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'turnstile_invalid')
        self.assertFalse(send_otp.called)
        self.assertTrue(siteverify.called)

    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_public_recovery_allows_password_reset_with_code(self, send_otp):
        response = self.client.post(
            '/api/auth/recuperar-password/',
            {'email': self.user.email},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        code = send_otp.call_args.args[1]
        confirm = self.client.post(
            '/api/auth/confirmar-recuperacion/',
            {'email': self.user.email, 'codigo': code, 'nueva_password': 'NewPass123!'},
            format='json',
        )

        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass123!'))
        self.assertTrue(OTPCode.objects.filter(email=self.user.email, tipo='recuperacion', verified=True).exists())

    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_public_recovery_uses_generic_response_for_unknown_email(self, send_otp):
        response = self.client.post(
            '/api/auth/recuperar-password/',
            {'email': 'missing@leadbook.local'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(send_otp.called)
        self.assertFalse(OTPCode.objects.filter(email='missing@leadbook.local', tipo='recuperacion').exists())

    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_public_recovery_wrong_code_increments_attempts(self, send_otp):
        self.client.post('/api/auth/recuperar-password/', {'email': self.user.email}, format='json')
        otp = OTPCode.objects.get(email=self.user.email, tipo='recuperacion')

        response = self.client.post(
            '/api/auth/confirmar-recuperacion/',
            {'email': self.user.email, 'codigo': '000000', 'nueva_password': 'NewPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)
        self.assertFalse(otp.verified)

    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_authenticated_password_change_with_code_keeps_session_alive(self, send_otp):
        self.client.force_authenticate(user=self.user)
        request_code = self.client.post('/api/auth/password-change-code/', {}, format='json')

        self.assertEqual(request_code.status_code, 200, request_code.content)
        code = send_otp.call_args.args[1]
        response = self.client.post(
            '/api/auth/cambiar-password/',
            {'codigo': code, 'new_password': 'NewPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('sessions_closed', body)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass123!'))

    @patch('api.tasks.send_otp_email_async', return_value='sent:test')
    def test_authenticated_password_change_rejects_unsafe_password(self, send_otp):
        self.client.force_authenticate(user=self.user)
        self.client.post('/api/auth/password-change-code/', {}, format='json')
        code = send_otp.call_args.args[1]

        response = self.client.post(
            '/api/auth/cambiar-password/',
            {'codigo': code, 'new_password': '12345678'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'password_insegura')

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from api.ai_services import APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError, call_cerebras_api
from api.models import (
    APIKey,
    AgentMediaAsset,
    CerebrasUsageLog,
    ComercialAgentProfile,
    ContentGenerationRun,
    Listado,
    Notificacion,
    OTPCode,
    Servicio,
    UsageLog,
    UserAPIAssignment,
)
from api.pool_manager import get_next_available_api
from api.services.listing_extractor import ExtractorError, extract_listing_from_url
from api.services.cerebras_models import sync_cerebras_key_models


class _FakeRawResponse:
    def __init__(self, content):
        self._content = content

    def read(self, *_args, **_kwargs):
        return self._content


class _FakeHttpResponse:
    is_redirect = False
    is_permanent_redirect = False
    status_code = 200

    def __init__(self, html, url='https://example.com/propiedad'):
        self.url = url
        self.headers = {'Content-Type': 'text/html; charset=utf-8'}
        self.raw = _FakeRawResponse(html.encode('utf-8'))
        self._content = b''

    @property
    def content(self):
        return self._content

    def raise_for_status(self):
        return None


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


class _FakeCerebrasModelsResponse:
    def __init__(self, payload, status_code=200, text=''):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload


class _FakeCerebrasChatResponse:
    def __init__(self, status_code, payload=None, text='', headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}
        self.content = b'{}' if payload is not None else b''

    def json(self):
        return self._payload


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


class CerebrasModelCascadeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='cerebras-cascade@leadbook.local',
            password='test-pass',
            nombre='Cerebras Cascade',
            plan_nombre='starter',
        )
        self.admin = get_user_model().objects.create_user(
            email='cerebras-admin@leadbook.local',
            password='test-pass',
            nombre='Cerebras Admin',
            is_staff=True,
        )
        self.service, _ = Servicio.objects.update_or_create(
            nombre='cerebras',
            defaults={'descripcion': 'Cerebras', 'default_daily_limit': 1000000},
        )
        APIKey.objects.filter(servicio=self.service).delete()

    def _create_key(self, api_key, **kwargs):
        defaults = {
            'servicio': self.service,
            'api_key': api_key,
            'status': 'available',
            'google_daily_limit': 1000000,
            'supported_models': ['gpt-oss-120b', 'zai-glm-4.7'],
        }
        defaults.update(kwargs)
        return APIKey.objects.create(**defaults)

    def _create_listing(self):
        return Listado.objects.create(
            agente=self.user,
            titulo='Casa Cerebras',
            tipo_propiedad='Casa',
            operacion='venta',
            ciudad='Buenos Aires',
            precio='100000',
        )

    @patch('api.services.cerebras_models.requests.get')
    def test_sync_cerebras_key_models_orders_known_models_first(self, mock_get):
        key = self._create_key('cerebras-sync-key', supported_models=[])
        mock_get.return_value = _FakeCerebrasModelsResponse({
            'data': [
                {'id': 'zai-glm-4.7'},
                {'id': 'future-model'},
                {'id': 'gpt-oss-120b'},
            ],
        })

        models = sync_cerebras_key_models(key)

        self.assertEqual(models, ['gpt-oss-120b', 'zai-glm-4.7', 'future-model'])
        key.refresh_from_db()
        self.assertEqual(key.supported_models, ['gpt-oss-120b', 'zai-glm-4.7', 'future-model'])
        self.assertIsNotNone(key.models_last_synced_at)
        self.assertEqual(key.models_last_error, '')

    @patch('api.views_admin.requests.get')
    def test_admin_pool_test_syncs_cerebras_supported_models(self, mock_get):
        self.client.force_authenticate(user=self.admin)
        key = self._create_key('cerebras-admin-key', supported_models=[])
        mock_get.return_value = _FakeCerebrasModelsResponse({
            'data': [
                {'id': 'zai-glm-4.7'},
                {'id': 'gpt-oss-120b'},
            ],
        })

        response = self.client.post(f'/api/admin/apikeys/pool/{key.id}/test/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['supported_models'], ['gpt-oss-120b', 'zai-glm-4.7'])
        key.refresh_from_db()
        self.assertEqual(key.supported_models, ['gpt-oss-120b', 'zai-glm-4.7'])
        self.assertIsNotNone(key.models_last_synced_at)

    @patch('api.ai_services.requests.post')
    def test_cerebras_generation_rotates_key_before_model_fallback(self, mock_post):
        key_a = self._create_key('cerebras-key-a')
        key_b = self._create_key('cerebras-key-b')
        listing = self._create_listing()
        run = ContentGenerationRun.objects.create(
            user=self.user,
            listado=listing,
            api_key=key_a,
            status='running',
            current_step='pdf',
        )
        mock_post.side_effect = [
            _FakeCerebrasChatResponse(500, text='temporary failure'),
            _FakeCerebrasChatResponse(200, {
                'choices': [{'message': {'content': 'contenido ok'}}],
                'usage': {'total_tokens': 321},
            }),
        ]

        result = call_cerebras_api(
            'Genera copy',
            agente=self.user,
            listado_id=listing.id,
            generation_run_id=run.id,
            generation_step='pdf',
            model='gpt-oss-120b',
            allow_model_fallback=True,
        )

        self.assertEqual(result, 'contenido ok')
        first_call = mock_post.call_args_list[0].kwargs
        second_call = mock_post.call_args_list[1].kwargs
        self.assertEqual(first_call['headers']['Authorization'], 'Bearer cerebras-key-a')
        self.assertEqual(second_call['headers']['Authorization'], 'Bearer cerebras-key-b')
        self.assertEqual(first_call['json']['model'], 'gpt-oss-120b')
        self.assertEqual(second_call['json']['model'], 'gpt-oss-120b')
        run.refresh_from_db()
        self.assertEqual(run.api_key_id, key_b.id)
        success_log = CerebrasUsageLog.objects.filter(success=True).latest('id')
        self.assertEqual(success_log.api_key_id, key_b.id)
        self.assertEqual(success_log.model, 'gpt-oss-120b')


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


class ListingExtractorTests(TestCase):
    def test_structured_extraction_success(self):
        html = '''
        <html><head><script type="application/ld+json">
        {"@type":"RealEstateListing","name":"Casa luminosa en Palermo","description":"Casa con patio y pileta.",
        "image":["/foto1.jpg","https://cdn.example.com/foto2.jpg"],
        "offers":{"price":"250000","priceCurrency":"USD"},
        "address":{"addressLocality":"Palermo","streetAddress":"Av. Siempre Viva 123"},
        "numberOfBedrooms":3,"numberOfBathroomsTotal":2,"floorSize":{"value":180},
        "amenityFeature":[{"name":"Piscina"},{"name":"Parrilla"}]}
        </script></head><body></body></html>
        '''
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor.requests.Session.get', return_value=_FakeHttpResponse(html)):
            result = extract_listing_from_url('https://example.com/propiedad')

        self.assertTrue(result['ok'])
        self.assertGreaterEqual(result['confidence'], 0.6)
        self.assertEqual(result['data']['titulo'], 'Casa luminosa en Palermo')
        self.assertEqual(result['data']['moneda'], 'USD')
        self.assertEqual(result['data']['recamaras'], 3)
        self.assertEqual(len(result['data']['fotos']), 2)
        self.assertEqual(len(result['media_candidates']), 2)
        self.assertEqual(result['required_action'], 'none')
        self.assertIn('extraction_id', result)

    def test_fallback_extraction_when_no_structured_data(self):
        html = '''
        <html><head><title>Departamento en venta</title><meta property="og:image" content="/hero.jpg"></head>
        <body><h1>Departamento en venta en Belgrano</h1>
        <p>Excelente departamento en venta con 2 habitaciones, 1 baño, 74 m2, balcon y cochera. USD 120.000.</p></body></html>
        '''
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor.requests.Session.get', return_value=_FakeHttpResponse(html)):
            result = extract_listing_from_url('https://example.com/depto')

        self.assertTrue(result['ok'])
        self.assertIn('semiestructurada', ' '.join(result['warnings']))
        self.assertEqual(result['data']['operacion'], 'venta')
        self.assertEqual(result['data']['recamaras'], 2)
        self.assertEqual(result['data']['moneda'], 'USD')

    def test_invalid_url_controlled_error(self):
        with self.assertRaises(ExtractorError) as ctx:
            extract_listing_from_url('ftp://example.com/a')
        self.assertEqual(ctx.exception.status_code, 400)

    @override_settings(IMPORT_URL_PLAYWRIGHT_ENABLED=True)
    def test_js_only_page_uses_playwright_when_enabled(self):
        empty_html = '<html><head><title>Cargando</title></head><body><div id="app"></div></body></html>'
        rendered_html = '''
        <html><head><meta property="og:image" content="https://cdn.example.com/rendered.jpg"></head>
        <body><h1>Casa renderizada en Punta</h1>
        <p>Casa en venta con 4 habitaciones, 3 banos, piscina y 320 m2. USD 900000.</p></body></html>
        '''
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor.requests.Session.get', return_value=_FakeHttpResponse(empty_html)), \
             patch('api.services.listing_extractor._render_html_with_playwright', return_value=(rendered_html, 'https://example.com/js')):
            result = extract_listing_from_url('https://example.com/js')

        self.assertTrue(result['ok'])
        self.assertEqual(result['mode'], 'playwright')
        self.assertEqual(result['data']['titulo'], 'Casa renderizada en Punta')
        self.assertEqual(result['media_candidates'][0], 'https://cdn.example.com/rendered.jpg')

    def test_blocked_page_returns_required_action(self):
        html = '<html><body><h1>Access denied</h1><p>Verify you are human. CAPTCHA required.</p></body></html>'
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor.requests.Session.get', return_value=_FakeHttpResponse(html)):
            result = extract_listing_from_url('https://example.com/blocked', use_playwright=False, use_unlocker=False)

        self.assertFalse(result['ok'])
        self.assertEqual(result['required_action'], 'manual_review')
        self.assertEqual(result['status'], 'needs_input')

    @override_settings(
        IMPORT_URL_PLAYWRIGHT_ENABLED=True,
        IMPORT_URL_UNLOCKER_ENABLED=True,
        BRIGHTDATA_UNLOCKER_TOKEN='token',
        BRIGHTDATA_UNLOCKER_ZONE='web_unlocker1',
    )
    def test_blocked_static_tries_playwright_then_unlocker(self):
        blocked = ExtractorError(
            'La pagina bloqueo la extraccion automatica.',
            status_code=200,
            required_action='blocked',
            extraction_status='needs_input',
        )
        unlocked_html = '''
        <html><head><meta property="og:image" content="https://cdn.example.com/unlocked.webp"></head>
        <body><h1>Residencia desbloqueada</h1>
        <p>Casa en venta con 4 habitaciones, 5 banos, terraza y 433 m2. USD 1323383.</p></body></html>
        '''

        class UnlockedResponse:
            url = 'https://example.com/blocked'
            content = unlocked_html.encode('utf-8')

        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor._fetch_html', side_effect=blocked), \
             patch('api.services.listing_extractor._render_html_with_playwright', side_effect=ExtractorError('Playwright bloqueado', required_action='blocked')) as playwright_mock, \
             patch('api.services.listing_extractor._fetch_html_with_unlocker', return_value=UnlockedResponse()) as unlocker_mock:
            result = extract_listing_from_url('https://example.com/blocked')

        self.assertTrue(result['ok'])
        self.assertEqual(result['mode'], 'unlocker')
        self.assertEqual(result['data']['titulo'], 'Residencia desbloqueada')
        self.assertEqual(result['media_candidates'][0], 'https://cdn.example.com/unlocked.webp')
        self.assertEqual(playwright_mock.call_count, 1)
        self.assertEqual(unlocker_mock.call_count, 1)
        self.assertEqual([item['mode'] for item in result['attempts']], ['static', 'playwright', 'unlocker'])
        self.assertEqual(result['attempts'][-1]['status'], 'success')

    @override_settings(
        IMPORT_URL_PLAYWRIGHT_ENABLED=True,
        IMPORT_URL_UNLOCKER_ENABLED=True,
        BRIGHTDATA_UNLOCKER_TOKEN='token',
        BRIGHTDATA_UNLOCKER_ZONE='web_unlocker1',
    )
    def test_all_providers_fail_returns_manual_review(self):
        blocked = ExtractorError(
            'La pagina bloqueo la extraccion automatica.',
            status_code=200,
            required_action='blocked',
            extraction_status='needs_input',
        )
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor._fetch_html', side_effect=blocked), \
             patch('api.services.listing_extractor._render_html_with_playwright', side_effect=ExtractorError('Playwright bloqueado', required_action='blocked')), \
             patch('api.services.listing_extractor._fetch_html_with_unlocker', side_effect=ExtractorError('Unlocker bloqueado', required_action='blocked')):
            result = extract_listing_from_url('https://example.com/blocked')

        self.assertFalse(result['ok'])
        self.assertEqual(result['required_action'], 'manual_review')
        self.assertEqual(result['status'], 'needs_input')
        self.assertEqual([item['mode'] for item in result['attempts']], ['static', 'playwright', 'unlocker'])

    @override_settings(IMPORT_URL_UNLOCKER_ENABLED=True, BRIGHTDATA_UNLOCKER_TOKEN='', BRIGHTDATA_UNLOCKER_ZONE='')
    def test_unlocker_without_credentials_returns_attempt_not_configured(self):
        blocked = ExtractorError(
            'La pagina bloqueo la extraccion automatica.',
            status_code=200,
            required_action='blocked',
            extraction_status='needs_input',
        )
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor._fetch_html', side_effect=blocked):
            result = extract_listing_from_url('https://example.com/blocked', use_playwright=False, use_unlocker=True)

        self.assertFalse(result['ok'])
        self.assertEqual(result['required_action'], 'manual_review')
        self.assertIn({'mode': 'unlocker', 'status': 'not_configured', 'reason': 'Proveedor anti-bot no configurado.'}, result['attempts'])

    @override_settings(
        IMPORT_URL_UNLOCKER_ENABLED=True,
        BRIGHTDATA_UNLOCKER_TOKEN='token',
        BRIGHTDATA_UNLOCKER_ZONE='web_unlocker1',
    )
    def test_brightdata_raw_html_response_extracts_data(self):
        blocked = ExtractorError(
            'La pagina bloqueo la extraccion automatica.',
            status_code=200,
            required_action='blocked',
            extraction_status='needs_input',
        )
        raw_html = '''
        <html><head><meta property="og:image" content="https://cdn.example.com/raw.webp"></head>
        <body><h1>Residencia raw</h1>
        <p>Casa en venta con 4 habitaciones, 5 banos y 433 m2. USD 1323383.</p></body></html>
        '''

        class RawUnlockerResponse:
            status_code = 200
            headers = {'Content-Type': 'text/html; charset=utf-8'}
            text = raw_html
            content = raw_html.encode('utf-8')

            def json(self):
                raise ValueError('raw html')

            def raise_for_status(self):
                return None

        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor._fetch_html', side_effect=blocked), \
             patch('api.services.listing_extractor.requests.post', return_value=RawUnlockerResponse()):
            result = extract_listing_from_url('https://example.com/raw', use_playwright=False, use_unlocker=True)

        self.assertTrue(result['ok'])
        self.assertEqual(result['mode'], 'unlocker')
        self.assertEqual(result['data']['titulo'], 'Residencia raw')
        self.assertEqual(result['media_candidates'][0], 'https://cdn.example.com/raw.webp')

    def test_unlocked_jamesedition_like_html_extracts_details_and_script_images(self):
        html = '''
        <html><head>
        <title>Panoramic Four Bedroom Sky Residence</title>
        <meta property="og:image" content="https://img.example.com/hero.webp">
        <script id="__NEXT_DATA__" type="application/json">
        {"props":{"gallery":["https:\\/\\/img.example.com\\/gallery-1.jpg","https:\\/\\/img.example.com\\/gallery-2.jpg"]}}
        </script>
        </head><body>
        <h1>Panoramic Four Bedroom Sky Residence</h1>
        <p>$1,323,383</p>
        <p>4 Beds 5 Baths 4,661 Sqft</p>
        <p>Al Omraneya, Giza Governorate, Egypt</p>
        <p>An expansive rhythm of space, light, and outdoor flow defines this 433 sqm four-bedroom residence with terrace and privacy.</p>
        </body></html>
        '''
        with patch('api.services.listing_extractor._assert_public_host'), \
             patch('api.services.listing_extractor.requests.Session.get', return_value=_FakeHttpResponse(html)):
            result = extract_listing_from_url('https://www.jamesedition.com/real_estate/demo')

        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['titulo'], 'Panoramic Four Bedroom Sky Residence')
        self.assertEqual(result['data']['precio'], '1,323,383')
        self.assertGreaterEqual(len(result['media_candidates']), 3)
        self.assertIn('https://img.example.com/gallery-1.jpg', result['media_candidates'])

    def test_private_local_url_is_still_blocked(self):
        with self.assertRaises(ExtractorError) as ctx:
            extract_listing_from_url('http://127.0.0.1/admin')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_pasted_text_fallback_extracts_manual_content(self):
        text = 'Casa en venta en Recoleta. USD 450000. 3 habitaciones, 2 banos, 160 m2, balcon y cochera.'
        with patch('api.services.listing_extractor._assert_public_host'):
            result = extract_listing_from_url('https://example.com/private', pasted_text=text)

        self.assertTrue(result['ok'])
        self.assertEqual(result['mode'], 'manual')
        self.assertEqual(result['data']['operacion'], 'venta')
        self.assertEqual(result['data']['recamaras'], 3)


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

    def test_extract_endpoint_integration(self):
        payload = {
            'ok': True,
            'extraction_id': 'ext-123',
            'status': 'ready',
            'source': 'example.com',
            'mode': 'static',
            'confidence': 0.82,
            'data': {'titulo': 'Casa importada', 'fotos': ['https://example.com/a.jpg']},
            'media_candidates': ['https://example.com/a.jpg'],
            'warnings': [],
            'required_action': 'none',
            'final_url': 'https://example.com/propiedad',
        }
        with patch('api.views.extract_listing_from_url', return_value=payload):
            response = self.client.post(
                reverse('extract_listado_from_url'),
                {'url': 'https://example.com/propiedad'},
                format='json',
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['data']['titulo'], 'Casa importada')
        self.assertEqual(response.json()['extraction_id'], 'ext-123')
        self.assertEqual(response.json()['media_candidates'], ['https://example.com/a.jpg'])
        self.assertEqual(response.json()['required_action'], 'none')

    def test_extract_endpoint_allows_starter_plan(self):
        starter_user = get_user_model().objects.create_user(
            email='starter-import-test@leadbook.local',
            password='test-pass',
            nombre='Starter Import',
            plan_nombre='starter',
            plan_activo=True,
        )
        self.client.force_authenticate(user=starter_user)
        payload = {
            'ok': True,
            'extraction_id': 'starter-ext-123',
            'status': 'ready',
            'source': 'example.com',
            'mode': 'static',
            'confidence': 0.78,
            'data': {'titulo': 'Depto importado'},
            'media_candidates': [],
            'warnings': [],
            'required_action': 'none',
            'final_url': 'https://example.com/depto',
        }
        with patch('api.views.extract_listing_from_url', return_value=payload):
            response = self.client.post(
                reverse('extract_listado_from_url'),
                {'url': 'https://example.com/depto'},
                format='json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['extraction_id'], 'starter-ext-123')

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

    def test_creating_listing_does_not_register_property_usage_until_content_ready(self):
        response = self.client.post(
            reverse('listados'),
            {
                'formData': {
                    'titulo': 'Casa sin contenidos',
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
        self.assertEqual(UsageLog.objects.filter(agent=self.user, tipo='property').count(), 0)
        quota = response.json()['daily_listing_quota']
        self.assertEqual(quota['used'], 0)
        self.assertEqual(quota['remaining'], 30)

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

    def test_upload_fotos_downloads_only_accepted_external_import_refs(self):
        accepted_cover = {
            'url': 'https://cdn.example.com/cover.webp',
            'source': 'external_import',
            'external_import': True,
        }
        accepted_gallery = {
            'url': 'https://cdn.example.com/gallery.webp',
            'source': 'external_import',
            'external_import': True,
        }
        removed_external = {
            'url': 'https://cdn.example.com/removed.webp',
            'source': 'external_import',
            'external_import': True,
        }

        downloaded_urls = []

        def fake_download(url, *args, **kwargs):
            downloaded_urls.append(url)
            return b'image-bytes', 'image/webp'

        def fake_upload(file_obj, user_id, listado_id=None, tipo_foto='portada', indice=0):
            stem = file_obj.name.rsplit('.', 1)[0]
            public_id = f'leadbook/listados/usuario_{user_id}/temp/foto_{stem}_{tipo_foto}_{indice}'
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

        with patch('api.views._download_remote_asset', side_effect=fake_download), \
             patch('api.services.almacenamiento.AlmacenamientoCloudinary.guardar_foto_propiedad_file', side_effect=fake_upload):
            response = self.client.post(
                reverse('upload_fotos_listado'),
                {
                    'mode': 'replace',
                    'delete_removed': True,
                    'download_remote': True,
                    'portadaUrl': accepted_cover,
                    'fotosRecorrido': [accepted_gallery],
                    'removedMediaRefs': [removed_external],
                },
                format='json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(downloaded_urls, ['https://cdn.example.com/cover.webp', 'https://cdn.example.com/gallery.webp'])
        self.assertIn('cover', payload['portadaUrl']['public_id'])
        self.assertEqual(len(payload['fotosRecorrido']), 1)
        self.assertIn('gallery', payload['fotosRecorrido'][0]['public_id'])

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

    def test_verify_otp_expired_message_is_clean(self):
        email = 'expired-otp@leadbook.local'
        code = '123456'
        OTPCode.objects.create(
            email=email,
            code_hash=OTPCode.hash_code(code),
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(
            '/api/auth/verify-otp/',
            {'email': email, 'code': code},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json().get('error'), 'Codigo expirado. Pedi uno nuevo.')
        self.assertNotIn('Ã', response.json().get('error', ''))

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

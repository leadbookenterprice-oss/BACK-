from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from unittest.mock import patch

from api.ai_services import GeminiQuotaExhaustedError, GeminiRateLimitedError
from api.models import AgentMediaAsset, ComercialAgentProfile, Listado
from api.services.listing_extractor import ExtractorError, extract_listing_from_url


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


class AdsStudioEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='ads-studio-test@leadbook.local',
            password='test-pass',
            nombre='Ads Tester',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_extract_endpoint_integration(self):
        payload = {
            'ok': True,
            'source': 'example.com',
            'confidence': 0.82,
            'data': {'titulo': 'Casa importada', 'fotos': ['https://example.com/a.jpg']},
            'warnings': [],
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

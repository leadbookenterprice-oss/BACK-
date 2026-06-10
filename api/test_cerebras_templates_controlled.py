from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from api.ai_services import call_cerebras_api, GeminiQuotaExhaustedError, GeminiRateLimitedError
from api.models import APIKey, APIRequestLog, CerebrasUsageLog, Servicio
from api.views import (
    _apply_template_tokens_to_html,
    _build_guaranteed_pdf_html,
    _ensure_pdf_contract_markers,
    _validate_generated_pdf_html,
)


class _FakeCerebrasResponse:
    def __init__(self, status_code=429, text='', headers=None, payload=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._payload = payload or {}
        self.content = b'{}' if status_code == 200 else b''

    def json(self):
        return self._payload


class CerebrasRateLimitClassificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='cerebras-rate-test@leadbook.local',
            password='pass12345',
            nombre='Cerebras Rate Test',
            plan_nombre='starter',
        )
        self.service, _ = Servicio.objects.get_or_create(
            nombre='cerebras',
            defaults={'descripcion': 'Cerebras', 'default_daily_limit': 1000000},
        )
        APIKey.objects.filter(servicio=self.service).delete()

    def _create_key(self):
        return APIKey.objects.create(
            servicio=self.service,
            api_key='ck-test-cerebras',
            status='available',
            google_daily_limit=1000000,
        )

    def test_429_rate_limit_does_not_exhaust_key(self):
        key = self._create_key()
        response = _FakeCerebrasResponse(
            status_code=429,
            text='rate limit exceeded: requests per minute',
            headers={'retry-after': '45'},
        )

        with patch('api.ai_services.requests.post', return_value=response):
            with self.assertRaises(GeminiRateLimitedError) as ctx:
                call_cerebras_api('caption prompt', agente=self.user, task='post_caption')

        key.refresh_from_db()
        self.assertEqual(ctx.exception.quota_state, 'soft_rate_limited')
        self.assertNotEqual(key.status, 'exhausted')

    def test_429_hard_quota_exhausts_key(self):
        key = self._create_key()
        response = _FakeCerebrasResponse(
            status_code=429,
            text='insufficient credits balance for this project',
            headers={'retry-after': '600'},
        )

        with patch('api.ai_services.requests.post', return_value=response):
            with self.assertRaises(GeminiQuotaExhaustedError) as ctx:
                call_cerebras_api('caption prompt', agente=self.user, task='post_caption')

        key.refresh_from_db()
        self.assertEqual(ctx.exception.quota_state, 'hard_exhausted')
        self.assertEqual(key.status, 'exhausted')

    def test_success_records_real_usage_tokens_not_estimated_max(self):
        key = self._create_key()
        response = _FakeCerebrasResponse(
            status_code=200,
            payload={
                'choices': [{'message': {'content': 'Caption listo'}}],
                'usage': {
                    'prompt_tokens': 12,
                    'completion_tokens': 18,
                    'total_tokens': 30,
                },
            },
        )

        with patch('api.ai_services.requests.post', return_value=response):
            result = call_cerebras_api(
                'caption prompt with enough length to estimate more than thirty tokens',
                agente=self.user,
                task='post_caption',
                max_completion_tokens=500,
            )

        key.refresh_from_db()
        usage_log = CerebrasUsageLog.objects.get(api_key=key)
        request_log = APIRequestLog.objects.get(api_key=key)
        self.assertEqual(result, 'Caption listo')
        self.assertEqual(key.slot_tokens_today, 30)
        self.assertEqual(usage_log.actual_tokens, 30)
        self.assertEqual(usage_log.charged_tokens, 30)
        self.assertEqual(usage_log.metadata['usage_prompt_tokens'], 12)
        self.assertEqual(usage_log.metadata['usage_completion_tokens'], 18)
        self.assertEqual(usage_log.metadata['token_count_source'], 'cerebras_usage')
        self.assertEqual(request_log.tokens_used, 30)


class TemplateContractTests(TestCase):
    def test_arena_clara_recolors_shared_tech_base(self):
        html = (
            '<html><head><style>'
            ':root{--brand-primary:#0d47a1;--brand-secondary:#1565c0;--brand-accent:#00e5ff;}'
            '</style></head><body>Template</body></html>'
        )

        themed = _apply_template_tokens_to_html(html, 'arena_clara', None)

        self.assertIn('data-template-id="arena_clara"', themed)
        self.assertIn('#6b5b49', themed)
        self.assertIn('#cda66d', themed)
        self.assertNotIn('#0d47a1', themed)

    def test_pdf_validation_rejects_web_like_missing_contract(self):
        errors = _validate_generated_pdf_html(
            '<html><body><nav>Inicio</nav><main>Propiedades</main></body></html>',
            {'template_id': 'arena_clara', 'descripcion': 'Descripcion real'},
        )

        self.assertIn('template_marker_missing', errors)
        self.assertIn('leadbook_pdf_marker_missing', errors)
        self.assertIn('looks_like_web_page', errors)

    def test_pdf_validation_accepts_required_contract(self):
        gallery_url = 'https://res.cloudinary.com/demo/image/upload/gallery.jpg'
        logo_url = 'https://res.cloudinary.com/demo/image/upload/logo.png'
        html = f'''
        <html lang="es" data-leadbook-pdf="true" data-template-id="arena_clara">
        <head><style>:root{{--brand-primary:#6b5b49;--brand-accent:#cda66d;}}</style></head>
        <body>
          <section data-section="hero"><img src="https://res.cloudinary.com/demo/image/upload/cover.jpg"></section>
          <section data-section="price">USD 100000</section>
          <section data-section="stats">2 banos</section>
          <section data-section="description">Descripcion</section>
          <section data-section="amenities">Amenidad pileta</section>
          <section data-section="gallery"><img src="{gallery_url}"></section>
          <section data-section="contact"><img src="{logo_url}">Contacto</section>
        </body></html>
        '''

        errors = _validate_generated_pdf_html(
            html,
            {
                'template_id': 'arena_clara',
                'descripcion': 'Descripcion real',
                'amenidades': ['Pileta'],
                'fotos_recorrido': [gallery_url],
                'logo_url': logo_url,
            },
        )

        self.assertEqual(errors, [])

    def test_pdf_contract_marker_repair_accepts_local_template_shape(self):
        gallery_url = 'https://res.cloudinary.com/demo/image/upload/gallery.jpg'
        logo_url = 'https://res.cloudinary.com/demo/image/upload/logo.png'
        html = f'''
        <html lang="es">
        <head><style>:root{{--primario:#0d47a1;--acento:#00e5ff;}}</style></head>
        <body>
          <div class="hero"><img src="https://res.cloudinary.com/demo/image/upload/cover.jpg"></div>
          <div class="precio-bar">USD 100000</div>
          <div class="stats">2 banos</div>
          <div class="descripcion">Descripcion real</div>
          <div class="amenidades">Amenidad pileta</div>
          <div class="galeria"><img src="{gallery_url}"></div>
          <div class="footer"><img src="{logo_url}">Contacto</div>
        </body></html>
        '''

        context = {
            'template_id': 'tech_modern',
            'descripcion': 'Descripcion real',
            'amenidades': ['Pileta'],
            'fotos_recorrido': [gallery_url],
            'logo_url': logo_url,
        }

        repaired = _ensure_pdf_contract_markers(html, context)
        errors = _validate_generated_pdf_html(repaired, context)

        self.assertIn('data-leadbook-pdf="true"', repaired)
        self.assertIn('data-template-id="tech_modern"', repaired)
        self.assertEqual(errors, [])

    def test_guaranteed_pdf_fallback_accepts_listing_context(self):
        gallery_url = 'https://res.cloudinary.com/demo/image/upload/gallery.jpg'
        logo_url = 'https://res.cloudinary.com/demo/image/upload/logo.png'
        context = {
            'template_id': 'arena_clara',
            'tipo_propiedad': 'Casa',
            'ciudad': 'Cairo',
            'operacion': 'Venta',
            'precio': '1500000',
            'moneda': 'USD',
            'recamaras': '4',
            'banos': '3',
            'superficie_total': '450 m2',
            'descripcion': 'Descripcion real de la propiedad.',
            'amenidades': ['Pileta', 'Terraza'],
            'portada_url': 'https://res.cloudinary.com/demo/image/upload/cover.jpg',
            'fotos_recorrido': [gallery_url],
            'logo_url': logo_url,
            'agencia_nombre': 'LeadBook Realty',
            'agente_nombre': 'Carlos Santos',
            'agente_telefono': '+5491100000000',
            'agente_email': 'carlos@example.com',
        }

        html = _build_guaranteed_pdf_html(context, 'arena_clara')
        errors = _validate_generated_pdf_html(html, context)

        self.assertEqual(errors, [])
        self.assertIn('data-leadbook-pdf="true"', html)
        self.assertIn('data-template-id="arena_clara"', html)
        self.assertIn(gallery_url, html)
        self.assertIn(logo_url, html)

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from api.models import ContentGenerationRun, Listado
from api.services.ai_limits import get_model_limit_config, load_ai_limits_config
from api.services.cerebras_generation_protocol import PROTOCOL_VERSION, create_generation_protocol
from api.services.content_generation import CONTENT_PACK_STEPS, start_or_resume_generation_run


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

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from api.models import APIKey, ContentGenerationRun, Listado, Servicio
from api.services.ai_limits import get_model_limit_config, load_ai_limits_config
from api.services.cerebras_generation_protocol import PROTOCOL_VERSION, create_generation_protocol
from api.services.content_generation import (
    CONTENT_PACK_STEPS,
    cooldown_generation_run_slot,
    reset_generation_step_for_retry,
    start_or_resume_generation_run,
)


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

    def test_cerebras_run_rotates_to_another_key_after_soft_cooldown(self):
        service, _ = Servicio.objects.get_or_create(
            nombre='cerebras',
            defaults={'descripcion': 'Cerebras', 'default_daily_limit': 1000000},
        )
        APIKey.objects.filter(servicio=service).delete()
        first_key = APIKey.objects.create(
            servicio=service,
            api_key='ck-first',
            status='available',
            google_daily_limit=1000000,
        )
        second_key = APIKey.objects.create(
            servicio=service,
            api_key='ck-second',
            status='available',
            google_daily_limit=1000000,
        )

        run, reservation = start_or_resume_generation_run(
            self.user,
            self.listado,
            metadata={'ai_provider': 'cerebras'},
        )
        self.assertIsNone(reservation['error'])
        self.assertEqual(run.api_key_id, first_key.id)

        cooldown_generation_run_slot(run, seconds=60, error_message='soft 429')
        reset_generation_step_for_retry(run, 'plan', error_message='soft 429')
        run.refresh_from_db()
        first_key.refresh_from_db()
        self.assertIsNone(run.api_key_id)
        self.assertIsNone(first_key.slot_locked_by_id)
        self.assertIsNone(first_key.slot_locked_listado_id)
        self.assertIsNotNone(first_key.slot_locked_until)

        rotated_run, second_reservation = start_or_resume_generation_run(
            self.user,
            self.listado,
            metadata={'ai_provider': 'cerebras'},
        )
        self.assertIsNone(second_reservation['error'])
        self.assertEqual(rotated_run.api_key_id, second_key.id)

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

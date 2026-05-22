from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory
from unittest.mock import patch

from api.models import FollowUpTask, Lead, LeadEvent, Listado, PipelineStage
from api.services.crm_service import CRMSoftRateLimited, create_or_get_lead
from api.views_crm import meta_leads_webhook


class CRMLeadServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='crm-service@leadbook.local',
            password='test-pass',
            nombre='CRM Tester',
        )

    def test_dedupes_by_meta_leadgen_id_and_keeps_single_followup(self):
        payload = {
            'leadgen_id': 'meta-123',
            'field_data': [
                {'name': 'full_name', 'values': ['Ana Gomez']},
                {'name': 'email', 'values': ['ANA@EXAMPLE.COM']},
                {'name': 'phone', 'values': ['+54 9 11 1234-5678']},
            ],
        }

        first, created_first, reason_first = create_or_get_lead(self.user, payload, origin='meta')
        second, created_second, reason_second = create_or_get_lead(self.user, payload, origin='meta')

        self.assertTrue(created_first)
        self.assertEqual(reason_first, '')
        self.assertFalse(created_second)
        self.assertEqual(reason_second, 'leadgen_id')
        self.assertEqual(first.id, second.id)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(FollowUpTask.objects.filter(lead=first, reason='initial_response').count(), 1)

    def test_dedupes_by_contact_listing_and_window(self):
        listing = Listado.objects.create(
            agente=self.user,
            titulo='Casa CRM',
            tipo_propiedad='casa',
            operacion='venta',
            ciudad='Palermo',
            precio='250000',
            moneda='USD',
        )
        payload = {'full_name': 'Juan Perez', 'email': 'juan@example.com', 'listing_id': listing.id}

        first, created_first, _ = create_or_get_lead(self.user, payload, origin='web')
        second, created_second, reason_second = create_or_get_lead(self.user, payload, origin='web')

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(reason_second, 'contact_window')
        self.assertEqual(first.id, second.id)
        self.assertEqual(Lead.objects.count(), 1)


class CRMEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='crm-endpoints@leadbook.local',
            password='test-pass',
            nombre='CRM Endpoint Tester',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_move_stage_creates_timeline_event(self):
        response = self.client.post(
            reverse('crm_leads_collection'),
            {'full_name': 'Maria Lead', 'email': 'maria@example.com', 'origin': 'manual'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        lead_id = response.json()['item']['id']
        target_stage = PipelineStage.objects.get(owner=self.user, slug='calificado')

        move_response = self.client.post(
            reverse('crm_lead_move_stage', kwargs={'lead_id': lead_id}),
            {'stage': 'calificado'},
            format='json',
        )

        self.assertEqual(move_response.status_code, 200, move_response.content)
        self.assertEqual(move_response.json()['pipeline_stage']['slug'], 'calificado')
        self.assertTrue(
            LeadEvent.objects.filter(
                lead_id=lead_id,
                event_type='stage_changed',
                metadata__to=target_stage.slug,
            ).exists()
        )

    def test_mark_contacted_completes_initial_followup_and_moves_to_contacted(self):
        lead, _, _ = create_or_get_lead(self.user, {'full_name': 'Sofia Lead', 'phone': '1133334444'})

        response = self.client.post(reverse('crm_lead_mark_contacted', kwargs={'lead_id': lead.id}), format='json')

        self.assertEqual(response.status_code, 200, response.content)
        lead.refresh_from_db()
        task = FollowUpTask.objects.get(lead=lead, reason='initial_response')
        self.assertIsNotNone(lead.first_response_at)
        self.assertEqual(lead.pipeline_stage.slug, 'contactado')
        self.assertEqual(task.status, 'done')


class MetaLeadsWebhookTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='meta-webhook@leadbook.local',
            password='test-pass',
            nombre='Meta Webhook Tester',
        )
        self.client = APIClient()

    def test_meta_webhook_is_idempotent_by_leadgen_id(self):
        payload = {
            'entry': [{
                'changes': [{
                    'value': {
                        'leadgen_id': 'leadgen-777',
                        'form_id': 'form-1',
                        'page_id': 'page-1',
                        'field_data': [
                            {'name': 'full_name', 'values': ['Laura Meta']},
                            {'name': 'email', 'values': ['laura@example.com']},
                        ],
                    },
                }],
            }],
        }
        url = f"{reverse('crm_meta_leads_webhook')}?owner_id={self.user.id}"

        with patch('api.views_crm._verify_meta_signature', return_value=True):
            first = self.client.post(url, payload, format='json')
            second = self.client.post(url, payload, format='json')

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertTrue(first.json()['results'][0]['created'])
        self.assertFalse(second.json()['results'][0]['created'])
        self.assertEqual(second.json()['results'][0]['dedupe_reason'], 'leadgen_id')
        self.assertEqual(Lead.objects.filter(owner=self.user, origin='meta').count(), 1)

    def test_meta_soft_rate_limit_returns_retryable_contract(self):
        factory = APIRequestFactory()
        request = factory.post(reverse('crm_meta_leads_webhook'), {'entry': []}, format='json')
        with patch('api.views_crm._verify_meta_signature', return_value=True), \
             patch('api.views_crm.ingest_meta_webhook', side_effect=CRMSoftRateLimited()):
            response = meta_leads_webhook(request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['error'], 'soft_rate_limited')
        self.assertTrue(response.data['retryable'])

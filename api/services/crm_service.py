import hashlib
import re
from datetime import timedelta

import requests
from decouple import config
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.utils import timezone
from django.utils.text import slugify

from api.models import Agent, FollowUpTask, Lead, LeadAssignment, LeadEvent, Listado, PipelineStage
from api.plan_utils import has_pro_feature_access


DEFAULT_PIPELINE_STAGES = [
    {'slug': 'nuevo', 'name': 'Nuevo', 'order': 10, 'color': '#00d4ff', 'is_default': True},
    {'slug': 'contactado', 'name': 'Contactado', 'order': 20, 'color': '#8b5cf6'},
    {'slug': 'calificado', 'name': 'Calificado', 'order': 30, 'color': '#22c55e'},
    {'slug': 'visita', 'name': 'Visita', 'order': 40, 'color': '#f59e0b'},
    {'slug': 'cierre', 'name': 'Cierre', 'order': 50, 'color': '#10b981'},
    {'slug': 'perdido', 'name': 'Perdido', 'order': 60, 'color': '#ef4444'},
]

CONTACT_FIELD_ALIASES = {
    'full_name': {'full_name', 'name', 'nombre', 'nombre_completo', 'first_name', 'last_name'},
    'email': {'email', 'correo', 'correo_electronico', 'e-mail'},
    'phone': {'phone', 'telefono', 'teléfono', 'mobile', 'phone_number', 'whatsapp'},
    'message': {'message', 'mensaje', 'consulta', 'comments', 'comentarios'},
}

RATE_LIMIT_CODES = {4, 17, 32, 613}


class CRMSoftRateLimited(Exception):
    pass


class CRMExternalProviderError(Exception):
    pass


def normalize_phone(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    prefix = '+' if raw.startswith('+') else ''
    digits = re.sub(r'\D+', '', raw)
    return f'{prefix}{digits}' if digits else ''


def normalize_email(value):
    return str(value or '').strip().lower()


def normalize_origin(value):
    origin = str(value or 'manual').strip().lower()
    allowed = {choice[0] for choice in Lead.ORIGIN_CHOICES}
    return origin if origin in allowed else 'manual'


def ensure_default_pipeline_stages(owner):
    stages = []
    for item in DEFAULT_PIPELINE_STAGES:
        stage, _ = PipelineStage.objects.get_or_create(
            owner=owner,
            slug=item['slug'],
            defaults={
                'name': item['name'],
                'order': item['order'],
                'color': item['color'],
                'is_default': item.get('is_default', False),
                'is_active': True,
            },
        )
        stages.append(stage)
    return PipelineStage.objects.filter(owner=owner, is_active=True).order_by('order', 'id')


def get_default_stage(owner):
    stages = ensure_default_pipeline_stages(owner)
    return stages.filter(slug='nuevo').first() or stages.first()


def get_stage(owner, stage_id=None, slug=None):
    ensure_default_pipeline_stages(owner)
    qs = PipelineStage.objects.filter(owner=owner, is_active=True)
    if stage_id:
        return qs.filter(id=stage_id).first()
    if slug:
        return qs.filter(slug=slugify(str(slug))).first()
    return get_default_stage(owner)


def _extract_field_data(payload):
    data = {}
    field_data = payload.get('field_data') or payload.get('fields') or []
    if isinstance(field_data, list):
        for item in field_data:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name') or item.get('key') or '').strip().lower()
            values = item.get('values') or item.get('value') or []
            if isinstance(values, list):
                value = values[0] if values else ''
            else:
                value = values
            if name:
                data[name] = value

    for key, value in payload.items():
        if isinstance(value, (str, int, float)) and key not in data:
            data[str(key).lower()] = value
    return data


def _pick_contact_field(fields, target):
    aliases = CONTACT_FIELD_ALIASES[target]
    if target == 'full_name':
        first = str(fields.get('first_name') or fields.get('nombre') or '').strip()
        last = str(fields.get('last_name') or fields.get('apellido') or '').strip()
        combined = ' '.join(part for part in [first, last] if part)
        if combined:
            return combined
    for key, value in fields.items():
        normalized_key = str(key or '').strip().lower()
        if normalized_key in aliases:
            return str(value or '').strip()
    return ''


def normalize_lead_payload(payload):
    fields = _extract_field_data(payload if isinstance(payload, dict) else {})
    full_name = _pick_contact_field(fields, 'full_name') or str(payload.get('full_name') or payload.get('name') or payload.get('nombre') or '').strip()
    email = normalize_email(_pick_contact_field(fields, 'email') or payload.get('email'))
    phone = normalize_phone(_pick_contact_field(fields, 'phone') or payload.get('phone') or payload.get('telefono'))
    message = _pick_contact_field(fields, 'message') or str(payload.get('message') or payload.get('mensaje') or '').strip()
    if not full_name:
        full_name = email or phone or 'Lead sin nombre'

    return {
        'full_name': full_name[:180],
        'email': email or None,
        'phone': phone or None,
        'message': message or None,
        'contact_data': fields,
    }


def resolve_listing(owner, listing_id):
    if not listing_id:
        return None
    try:
        return Listado.objects.filter(id=int(listing_id), agente=owner).first()
    except (TypeError, ValueError):
        return None


def resolve_meta_owner(payload, request=None):
    query_owner = request.query_params.get('owner_id') if request is not None else None
    owner_id = query_owner or payload.get('owner_id') or payload.get('agent_id') or payload.get('user_id')
    if owner_id:
        try:
            owner = Agent.objects.filter(id=int(owner_id), is_active=True).first()
            if owner:
                return owner
        except (TypeError, ValueError):
            pass

    page_id = str(payload.get('page_id') or '').strip()
    if page_id:
        owner = Agent.objects.filter(meta_instagram_account_id=page_id, is_active=True).first()
        if owner:
            return owner

    default_owner_id = config('CRM_META_DEFAULT_OWNER_ID', default='').strip()
    if default_owner_id:
        try:
            return Agent.objects.filter(id=int(default_owner_id), is_active=True).first()
        except (TypeError, ValueError):
            return None
    return None


def _dedupe_hash(owner, origin, email, phone, listing):
    raw = '|'.join([
        str(owner.id),
        origin,
        email or '',
        phone or '',
        str(listing.id if listing else ''),
    ])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def find_existing_lead(owner, origin, leadgen_id=None, email=None, phone=None, listing=None):
    if leadgen_id:
        existing = Lead.objects.filter(owner=owner, origin=origin, leadgen_id=leadgen_id).first()
        if existing:
            return existing, 'leadgen_id'

    if not email and not phone:
        return None, ''

    hours = config('CRM_LEAD_DEDUPE_WINDOW_HOURS', default=72, cast=int)
    cutoff = timezone.now() - timedelta(hours=max(1, hours))
    qs = Lead.objects.filter(owner=owner, origin=origin, created_at__gte=cutoff)
    if listing:
        qs = qs.filter(listing=listing)
    else:
        qs = qs.filter(listing__isnull=True)

    contact_filter = Q()
    if email:
        contact_filter |= Q(email=email)
    if phone:
        contact_filter |= Q(phone=phone)
    existing = qs.filter(contact_filter).order_by('-created_at').first()
    return (existing, 'contact_window') if existing else (None, '')


def create_lead_event(lead, event_type, title, message='', metadata=None, created_by=None):
    return LeadEvent.objects.create(
        lead=lead,
        owner=lead.owner,
        event_type=event_type,
        title=title,
        message=message or '',
        metadata=metadata or {},
        created_by=created_by,
    )


def create_initial_followup(lead):
    task = FollowUpTask.objects.create(
        lead=lead,
        owner=lead.owner,
        assigned_to=lead.assigned_to,
        title='Responder lead ahora',
        due_at=timezone.now(),
        priority='high',
        reason='initial_response',
    )
    create_lead_event(lead, 'followup_created', 'Tarea de seguimiento creada', metadata={'task_id': task.id})
    return task


def create_assignment(lead, assigned_to=None, assigned_by=None):
    LeadAssignment.objects.filter(lead=lead, is_active=True).update(is_active=False)
    assignment = LeadAssignment.objects.create(
        lead=lead,
        owner=lead.owner,
        assigned_to=assigned_to,
        assigned_by=assigned_by,
        is_active=True,
    )
    create_lead_event(
        lead,
        'assigned',
        'Lead asignado',
        metadata={'assigned_to': assigned_to.id if assigned_to else None, 'assignment_id': assignment.id},
        created_by=assigned_by,
    )
    return assignment


@transaction.atomic
def create_or_get_lead(owner, payload, origin='manual', created_by=None):
    origin = normalize_origin(origin)
    ensure_default_pipeline_stages(owner)
    normalized = normalize_lead_payload(payload)
    leadgen_id = str(payload.get('leadgen_id') or payload.get('leadgen_id') or payload.get('id') or '').strip() or None
    listing = resolve_listing(owner, payload.get('listing_id') or payload.get('listado_id'))
    existing, reason = find_existing_lead(
        owner,
        origin,
        leadgen_id=leadgen_id,
        email=normalized['email'],
        phone=normalized['phone'],
        listing=listing,
    )
    if existing:
        return existing, False, reason

    stage = get_default_stage(owner)
    now = timezone.now()
    sla_minutes = config('CRM_LEAD_SLA_MINUTES', default=15, cast=int)
    lead = Lead.objects.create(
        owner=owner,
        pipeline_stage=stage,
        assigned_to=owner,
        listing=listing,
        origin=origin,
        full_name=normalized['full_name'],
        email=normalized['email'],
        phone=normalized['phone'],
        message=normalized['message'],
        contact_data=normalized['contact_data'],
        leadgen_id=leadgen_id,
        form_id=str(payload.get('form_id') or '').strip() or None,
        page_id=str(payload.get('page_id') or '').strip() or None,
        campaign_id=str(payload.get('campaign_id') or '').strip() or None,
        campaign_name=str(payload.get('campaign_name') or '').strip() or None,
        adset_id=str(payload.get('adset_id') or '').strip() or None,
        ad_id=str(payload.get('ad_id') or '').strip() or None,
        raw_payload=payload,
        dedupe_key=_dedupe_hash(owner, origin, normalized['email'], normalized['phone'], listing),
        sla_due_at=now + timedelta(minutes=max(1, sla_minutes)),
    )
    create_lead_event(lead, 'created', 'Lead creado', metadata={'origin': origin}, created_by=created_by)
    if origin == 'meta':
        create_lead_event(lead, 'webhook_received', 'Webhook Meta recibido', metadata={'leadgen_id': leadgen_id})
    create_assignment(lead, assigned_to=owner, assigned_by=created_by)
    create_initial_followup(lead)
    return lead, True, ''


def move_lead_stage(lead, stage, user=None):
    previous = lead.pipeline_stage
    if previous_id := getattr(previous, 'id', None):
        if previous_id == stage.id:
            return lead
    lead.pipeline_stage = stage
    lead.status = 'won' if stage.slug == 'cierre' else ('lost' if stage.slug == 'perdido' else 'open')
    lead.save(update_fields=['pipeline_stage', 'status', 'updated_at'])
    create_lead_event(
        lead,
        'stage_changed',
        'Lead movido de etapa',
        metadata={
            'from': previous.slug if previous else None,
            'to': stage.slug,
            'from_name': previous.name if previous else None,
            'to_name': stage.name,
        },
        created_by=user,
    )
    return lead


def mark_lead_contacted(lead, user=None, message='Contacto registrado'):
    now = timezone.now()
    updates = ['last_contact_at', 'updated_at']
    lead.last_contact_at = now
    if not lead.first_response_at:
        lead.first_response_at = now
        updates.append('first_response_at')
    lead.save(update_fields=updates)
    FollowUpTask.objects.filter(lead=lead, status='pending', reason='initial_response').update(status='done', completed_at=now)
    create_lead_event(lead, 'contacted', message, created_by=user)
    return lead


def iter_meta_lead_payloads(payload):
    if not isinstance(payload, dict):
        return []
    entries = payload.get('entry')
    if not isinstance(entries, list):
        return [payload]

    items = []
    root_context = {k: payload.get(k) for k in ('owner_id', 'agent_id', 'user_id', 'listing_id', 'listado_id') if payload.get(k)}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get('changes') if isinstance(entry.get('changes'), list) else []
        for change in changes:
            value = change.get('value') if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            item = {
                **root_context,
                **{k: entry.get(k) for k in ('id', 'time') if entry.get(k)},
                **value,
            }
            if 'leadgen_id' not in item and value.get('leadgen_id'):
                item['leadgen_id'] = value.get('leadgen_id')
            items.append(item)
    return items


def fetch_meta_lead_details(leadgen_id, access_token):
    if not leadgen_id or not access_token:
        return {}
    url = f'https://graph.facebook.com/v19.0/{leadgen_id}'
    try:
        response = requests.get(
            url,
            params={'fields': 'id,created_time,field_data,form_id,ad_id,adset_id,campaign_id', 'access_token': access_token},
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        raise CRMExternalProviderError(str(exc)) from exc

    try:
        data = response.json()
    except ValueError:
        data = {}
    error = data.get('error') if isinstance(data, dict) else None
    error_code = int(error.get('code', 0) or 0) if isinstance(error, dict) else 0
    if response.status_code == 429 or error_code in RATE_LIMIT_CODES:
        raise CRMSoftRateLimited('Meta rate limited lead fetch')
    if response.status_code >= 400:
        raise CRMExternalProviderError(str(error or data or response.status_code))
    return data if isinstance(data, dict) else {}


def ingest_meta_webhook(payload, request=None):
    results = []
    for item in iter_meta_lead_payloads(payload):
        owner = resolve_meta_owner(item, request=request)
        if not owner:
            results.append({'created': False, 'error': 'owner_not_found', 'leadgen_id': item.get('leadgen_id')})
            continue
        if not has_pro_feature_access(owner):
            results.append({'created': False, 'error': 'crm_plan_required', 'leadgen_id': item.get('leadgen_id')})
            continue

        if item.get('leadgen_id') and not item.get('field_data'):
            token = getattr(owner, 'meta_access_token', None) or getattr(settings, 'META_ACCESS_TOKEN', '') or config('META_ACCESS_TOKEN', default='')
            if token:
                details = fetch_meta_lead_details(item.get('leadgen_id'), token)
                item = {**item, **details, 'leadgen_id': item.get('leadgen_id') or details.get('id')}

        lead, created, dedupe_reason = create_or_get_lead(owner, item, origin='meta')
        results.append({'lead_id': lead.id, 'created': created, 'dedupe_reason': dedupe_reason, 'leadgen_id': lead.leadgen_id})
    return results


def crm_metrics(owner):
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    leads = Lead.objects.filter(owner=owner)
    responded = leads.filter(first_response_at__isnull=False)
    avg_response = responded.annotate(delta=F('first_response_at') - F('created_at')).aggregate(avg=Avg('delta'))['avg']
    stage_counts = list(
        leads.values('pipeline_stage__slug', 'pipeline_stage__name')
        .annotate(count=Count('id'))
        .order_by('pipeline_stage__order')
    )
    return {
        'new_today': leads.filter(created_at__gte=day_start).count(),
        'new_week': leads.filter(created_at__gte=week_start).count(),
        'avg_first_response_seconds': int(avg_response.total_seconds()) if avg_response else None,
        'stage_counts': stage_counts,
        'sla_overdue': leads.filter(first_response_at__isnull=True, sla_due_at__lt=now).count(),
    }

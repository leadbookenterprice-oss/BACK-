from django.utils import timezone


PLAN_VIDEO_PRIORITY = {
    'business': 400,
    'scale': 300,
    'pro': 200,
    'starter': 100,
}


def get_plan_video_priority(user):
    plan = str(getattr(user, 'plan_nombre', '') or 'starter').strip().lower()
    return PLAN_VIDEO_PRIORITY.get(plan, PLAN_VIDEO_PRIORITY['starter'])


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = timezone.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except Exception:
        return None


def mark_video_queued(listado, provider):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    now = timezone.now()
    priority = get_plan_video_priority(listado.agente)
    datos['video_queue'] = {
        'provider': provider,
        'priority': priority,
        'plan': str(getattr(listado.agente, 'plan_nombre', '') or 'starter').lower(),
        'queued_at': now.isoformat(),
    }
    datos.pop('video_error', None)
    listado.datos_extra = datos
    listado.video_status = 'queued'
    listado.video_url = None
    listado.save(update_fields=['datos_extra', 'video_status', 'video_url', 'updated_at'])
    return datos['video_queue']


def get_video_queue_metadata(listado):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    queue = datos.get('video_queue') if isinstance(datos.get('video_queue'), dict) else {}
    priority = queue.get('priority')
    try:
        priority = int(priority)
    except Exception:
        priority = get_plan_video_priority(listado.agente)
    queued_at = _parse_dt(queue.get('queued_at')) or listado.updated_at or listado.creado_en or timezone.now()
    return {
        'provider': queue.get('provider') or datos.get('video_provider') or '',
        'priority': priority,
        'plan': queue.get('plan') or str(getattr(listado.agente, 'plan_nombre', '') or 'starter').lower(),
        'queued_at': queued_at,
    }


def sort_video_queue(listados):
    return sorted(
        listados,
        key=lambda item: (
            -get_video_queue_metadata(item)['priority'],
            get_video_queue_metadata(item)['queued_at'],
            item.id,
        ),
    )


def get_video_queue_position(listado, candidates=None):
    if listado.video_status != 'queued':
        return None
    if candidates is None:
        from api.models import Listado
        candidates = Listado.objects.filter(video_status='queued').select_related('agente')[:250]
    ordered = sort_video_queue(candidates)
    for index, item in enumerate(ordered, start=1):
        if item.id == listado.id:
            return index
    return None

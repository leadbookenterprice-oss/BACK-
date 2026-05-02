from django.utils import timezone
from api.models import APIKey, APIBundle, APIBundleAssignment, AdminAlert


class APIPoolService:

    # ── Bundle Operations ────────────────────────────────────────────────────

    @staticmethod
    def assign_bundle_to_user(user):
        """
        Asigna un bundle disponible y completo al usuario.
        Devuelve (bundle, created) o (None, False) si no hay bundles.
        """
        # Si ya tiene uno activo, no asignar otro
        if APIBundleAssignment.objects.filter(usuario=user, activo=True).exists():
            asig = APIBundleAssignment.objects.get(usuario=user, activo=True)
            return asig.bundle, False

        bundle = APIBundle.objects.filter(status='available').select_related(
            'key_gemini', 'key_elevenlabs', 'key_uploadpost'
        ).first()

        if not bundle or not bundle.is_complete():
            AdminAlert.objects.create(
                type='quota_warning',
                severity='critical',
                title='Sin bundles disponibles',
                message=f'Se intentó asignar un bundle a {user.email} pero no hay bundles completos disponibles.',
                related_user=user
            )
            return None, False

        bundle.status = 'assigned'
        bundle.save(update_fields=['status'])

        asig = APIBundleAssignment.objects.create(bundle=bundle, usuario=user)
        return bundle, True

    @staticmethod
    def release_bundle_from_user(user):
        """Libera el bundle de un usuario y lo pone disponible de nuevo."""
        try:
            asig = APIBundleAssignment.objects.get(usuario=user, activo=True)
            asig.activo = False
            asig.liberado_en = timezone.now()
            asig.save()

            asig.bundle.status = 'available'
            asig.bundle.save(update_fields=['status'])
            return True
        except APIBundleAssignment.DoesNotExist:
            return False

    @staticmethod
    def rotate_bundle(user):
        """
        Libera el bundle actual y asigna uno nuevo (para cuando el bundle
        falla o está agotado).
        """
        APIPoolService.release_bundle_from_user(user)
        bundle, created = APIPoolService.assign_bundle_to_user(user)
        if not bundle:
            AdminAlert.objects.create(
                type='quota_warning',
                severity='critical',
                title='Fallo al rotar bundle',
                message=f'No se pudo asignar un nuevo bundle a {user.email} porque el pool está vacío.',
                related_user=user
            )
        return bundle

    @staticmethod
    def get_bundle_stats():
        """Resumen del estado del pool de bundles."""
        total = APIBundle.objects.count()
        disponibles = APIBundle.objects.filter(status='available').count()
        asignados = APIBundle.objects.filter(status='assigned').count()
        retirados = APIBundle.objects.filter(status='retired').count()
        incompletos = sum(1 for b in APIBundle.objects.filter(status='available')
                          if not b.is_complete())
        return {
            'total': total,
            'disponibles': disponibles,
            'asignados': asignados,
            'retirados': retirados,
            'incompletos': incompletos,
        }

    # ── Key Operations (Legacy / Individual) ────────────────────────────────

    @staticmethod
    def assign_keys_to_user(user):
        """
        Compatibilidad hacia atrás: intenta asignar un bundle.
        Si no hay bundles, cae al sistema legacy de keys individuales.
        """
        bundle, created = APIPoolService.assign_bundle_to_user(user)
        if bundle:
            return ['gemini', 'elevenlabs', 'uploadpost']

        # Fallback legacy
        servicios = ['gemini', 'elevenlabs', 'uploadpost']
        asignadas = []
        for s in servicios:
            if APIKey.objects.filter(assigned_to=user, servicio=s).exists():
                continue
            key = APIKey.objects.filter(status='available', servicio=s).first()
            if key:
                key.status = 'assigned'
                key.assigned_to = user
                key.assigned_at = timezone.now()
                key.save()
                asignadas.append(s)
        return asignadas

    @staticmethod
    def release_keys_from_user(user):
        """Libera bundle y keys legacy de un usuario."""
        APIPoolService.release_bundle_from_user(user)
        keys = APIKey.objects.filter(assigned_to=user)
        for key in keys:
            key.status = 'available'
            key.assigned_to = None
            key.assigned_at = None
            key.requests_today = 0
            key.save()

    @staticmethod
    def mark_key_dead(key):
        """Marca una key como muerta y alerta al admin."""
        user = key.assigned_to
        key.status = 'dead'
        key.assigned_to = None
        key.save()

        AdminAlert.objects.create(
            type='api_dead',
            severity='critical',
            title=f'Key muerta: {key.servicio}',
            message=f'La key ID {key.id} ({key.label or key.api_key[:12]}) ha sido marcada como muerta.',
            related_api_key=key
        )

        if user:
            APIPoolService.rotate_bundle(user)

    @staticmethod
    def get_pool_stats():
        """Stats del pool completo (bundles + keys individuales)."""
        from django.db.models import Count
        bundle_stats = APIPoolService.get_bundle_stats()
        key_stats = list(APIKey.objects.values('servicio', 'status').annotate(total=Count('id')))
        return {
            'bundles': bundle_stats,
            'keys': key_stats,
        }

import base64
from typing import Any, Dict, Tuple

from django.core.management.base import BaseCommand

from api.models import Listado
from api.services.almacenamiento import AlmacenamientoCloudinary


class Command(BaseCommand):
    help = (
        "Limpia data-uri legacy en Listado.datos_extra. "
        "Por defecto corre en dry-run (sin persistir)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Persiste cambios en DB (por defecto es dry-run).',
        )
        parser.add_argument(
            '--purge-only',
            action='store_true',
            help='No intenta convertir data:image, solo purga.',
        )
        parser.add_argument(
            '--listado-id',
            dest='listado_ids',
            action='append',
            type=int,
            help='Procesa solo un listado_id. Se puede repetir.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Límite máximo de listados a escanear (0 = sin límite).',
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get('apply'))
        convert_images = not bool(options.get('purge_only'))
        listado_ids = options.get('listado_ids') or []
        limit = int(options.get('limit') or 0)
        dry_run = not apply_changes

        queryset = Listado.objects.select_related('agente').all().order_by('id')
        if listado_ids:
            queryset = queryset.filter(id__in=listado_ids)
        if limit > 0:
            queryset = queryset[:limit]

        summary = {
            'scanned': 0,
            'affected': 0,
            'updated': 0,
            'found_total': 0,
            'found_images': 0,
            'found_other_data_uri': 0,
            'convertible_images': 0,
            'non_convertible_images': 0,
            'would_convert': 0,
            'would_purge': 0,
            'converted': 0,
            'purged': 0,
            'failed_conversions': 0,
        }

        self.stdout.write(
            f"[BASE64-CLEANUP] mode={'APPLY' if apply_changes else 'DRY-RUN'} "
            f"convert_images={convert_images} limit={limit or 'all'}"
        )

        for listado in queryset.iterator():
            summary['scanned'] += 1
            datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
            counters = self._empty_counters()
            state = {'image_index': 0}

            transformed, changed = self._walk_value(
                value=datos,
                listado=listado,
                path='datos_extra',
                dry_run=dry_run,
                convert_images=convert_images,
                counters=counters,
                state=state,
            )

            if counters['found_total'] <= 0:
                continue

            summary['affected'] += 1
            for key in (
                'found_total',
                'found_images',
                'found_other_data_uri',
                'convertible_images',
                'non_convertible_images',
                'would_convert',
                'would_purge',
                'converted',
                'purged',
                'failed_conversions',
            ):
                summary[key] += counters[key]

            self.stdout.write(
                "[BASE64-CLEANUP] "
                f"listado_id={listado.id} "
                f"found={counters['found_total']} "
                f"images={counters['found_images']} "
                f"convertible={counters['convertible_images']} "
                f"would_convert={counters['would_convert']} "
                f"would_purge={counters['would_purge']} "
                f"converted={counters['converted']} "
                f"purged={counters['purged']} "
                f"failed_conversions={counters['failed_conversions']}"
            )

            if apply_changes and changed:
                listado.datos_extra = transformed if isinstance(transformed, dict) else {}
                listado.save(update_fields=['datos_extra', 'updated_at'])
                summary['updated'] += 1

        self.stdout.write('[BASE64-CLEANUP] summary:')
        for key, value in summary.items():
            self.stdout.write(f"  - {key}: {value}")

    @staticmethod
    def _empty_counters() -> Dict[str, int]:
        return {
            'found_total': 0,
            'found_images': 0,
            'found_other_data_uri': 0,
            'convertible_images': 0,
            'non_convertible_images': 0,
            'would_convert': 0,
            'would_purge': 0,
            'converted': 0,
            'purged': 0,
            'failed_conversions': 0,
        }

    def _walk_value(
        self,
        *,
        value: Any,
        listado: Listado,
        path: str,
        dry_run: bool,
        convert_images: bool,
        counters: Dict[str, int],
        state: Dict[str, int],
    ) -> Tuple[Any, bool]:
        if isinstance(value, str):
            return self._process_string(
                value=value,
                listado=listado,
                path=path,
                dry_run=dry_run,
                convert_images=convert_images,
                counters=counters,
                state=state,
            )

        if isinstance(value, list):
            changed = False
            output = []
            for index, item in enumerate(value):
                next_item, item_changed = self._walk_value(
                    value=item,
                    listado=listado,
                    path=f'{path}[{index}]',
                    dry_run=dry_run,
                    convert_images=convert_images,
                    counters=counters,
                    state=state,
                )
                if not dry_run and next_item is None:
                    changed = True
                    continue
                output.append(next_item)
                changed = changed or item_changed
            return (value, False) if dry_run else (output, changed)

        if isinstance(value, dict):
            changed = False
            output = {}
            for key, item in value.items():
                next_item, item_changed = self._walk_value(
                    value=item,
                    listado=listado,
                    path=f'{path}.{key}',
                    dry_run=dry_run,
                    convert_images=convert_images,
                    counters=counters,
                    state=state,
                )
                if not dry_run and next_item is None:
                    changed = True
                    continue
                output[key] = next_item
                changed = changed or item_changed
            return (value, False) if dry_run else (output, changed)

        return value, False

    def _process_string(
        self,
        *,
        value: str,
        listado: Listado,
        path: str,
        dry_run: bool,
        convert_images: bool,
        counters: Dict[str, int],
        state: Dict[str, int],
    ) -> Tuple[Any, bool]:
        stripped = value.strip()
        lowered = stripped.lower()
        if not lowered.startswith('data:'):
            return value, False

        counters['found_total'] += 1

        if lowered.startswith('data:image'):
            counters['found_images'] += 1
            is_convertible = self._is_convertible_data_image(stripped)
            if is_convertible:
                counters['convertible_images'] += 1
            else:
                counters['non_convertible_images'] += 1

            if dry_run:
                if convert_images and is_convertible:
                    counters['would_convert'] += 1
                else:
                    counters['would_purge'] += 1
                return value, False

            if convert_images and is_convertible:
                idx = state.get('image_index', 0)
                state['image_index'] = idx + 1
                uploaded = AlmacenamientoCloudinary.guardar_foto_propiedad(
                    base64_str=stripped,
                    user_id=listado.agente_id,
                    listado_id=listado.id,
                    tipo_foto='legacy',
                    indice=idx,
                )
                uploaded_url = self._extract_media_url(uploaded)
                if uploaded_url:
                    counters['converted'] += 1
                    return uploaded_url, True
                counters['failed_conversions'] += 1

            counters['purged'] += 1
            return None, True

        counters['found_other_data_uri'] += 1
        if dry_run:
            counters['would_purge'] += 1
            return value, False

        counters['purged'] += 1
        return None, True

    @staticmethod
    def _extract_media_url(uploaded: Any) -> str:
        if isinstance(uploaded, str):
            return uploaded if uploaded.startswith('http') else ''
        if isinstance(uploaded, dict):
            for key in ('url', 'secure_url'):
                candidate = uploaded.get(key)
                if isinstance(candidate, str) and candidate.startswith('http'):
                    return candidate
        return ''

    @staticmethod
    def _is_convertible_data_image(value: str) -> bool:
        try:
            if ',' not in value:
                return False
            header, payload = value.split(',', 1)
            if not header.lower().startswith('data:image'):
                return False
            base64.b64decode(payload, validate=True)
            return True
        except Exception:
            return False

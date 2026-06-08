from pathlib import Path

from django.core.management.base import BaseCommand

from api.ai_services import generar_html_desde_template
from api.services.template_contracts import BASE_LAYOUT_BY_TEMPLATE, TEMPLATE_IDS, get_template_contract
from api.views import (
    TEMPLATE_CAROUSEL_MAP,
    TEMPLATE_EMAIL_MAP,
    TEMPLATE_POST_MAP,
    TEMPLATE_STORY_MAP,
    _apply_template_tokens_to_html,
    _brand_template_demo_context,
    _default_tokens_for_base_template,
    _render_brand_template_preview_html,
)


MOJIBAKE_MARKERS = ('Ã', 'Â', 'â€', 'â€™', 'â€œ', '�')


class Command(BaseCommand):
    help = 'Audita los 10 templates LeadBook sin llamar a Cerebras ni subir media.'

    def handle(self, *args, **options):
        failures = []
        for template_id in TEMPLATE_IDS:
            contract = get_template_contract(template_id)
            if not contract:
                failures.append(f'{template_id}: contrato faltante')
                continue

            tokens = _default_tokens_for_base_template(template_id)
            demo_context = _brand_template_demo_context()
            demo_context.update({
                'template_id': template_id,
                'template_tokens': tokens,
                'fotos_recorrido_raw': demo_context.get('fotos_recorrido') or [],
                'logo_url_raw': demo_context.get('logo_url') or '',
            })

            self._check_map_file(template_id, 'post', TEMPLATE_POST_MAP, failures)
            self._check_map_file(template_id, 'story', TEMPLATE_STORY_MAP, failures)
            self._check_map_file(template_id, 'carrusel', TEMPLATE_CAROUSEL_MAP, failures)
            self._check_map_file(template_id, 'email', TEMPLATE_EMAIL_MAP, failures)

            for fmt in ('post', 'story', 'carousel', 'email'):
                try:
                    html, _, _, _ = _render_brand_template_preview_html(template_id, tokens, fmt)
                    self._check_html(template_id, fmt, html, contract, failures)
                except Exception as exc:
                    failures.append(f'{template_id}/{fmt}: render fallo {exc.__class__.__name__}: {exc}')

            try:
                pdf_html = generar_html_desde_template(dict(demo_context), agente=None)
                pdf_html = _apply_template_tokens_to_html(pdf_html, template_id, tokens)
                self._check_html(template_id, 'pdf', pdf_html, contract, failures)
            except Exception as exc:
                failures.append(f'{template_id}/pdf: render fallo {exc.__class__.__name__}: {exc}')

        if failures:
            for item in failures:
                self.stderr.write(self.style.ERROR(item))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f'Templates OK: {len(TEMPLATE_IDS)} templates auditados.'))

    def _check_map_file(self, template_id, fmt, mapping, failures):
        template_path = mapping.get(template_id)
        if not template_path:
            failures.append(f'{template_id}/{fmt}: mapping faltante')
            return
        full_path = Path('templates') / template_path
        if not full_path.exists():
            failures.append(f'{template_id}/{fmt}: archivo faltante {full_path}')

    def _check_html(self, template_id, fmt, html, contract, failures):
        source = str(html or '')
        lowered = source.lower()
        if '{{' in source or '}}' in source:
            failures.append(f'{template_id}/{fmt}: placeholders sin resolver')
        if any(marker in source for marker in MOJIBAKE_MARKERS):
            failures.append(f'{template_id}/{fmt}: posible mojibake')

        colors = contract.get('colors') or {}
        for color_key in ('primary', 'accent'):
            color = str(colors.get(color_key) or '').lower()
            if color and color not in lowered:
                failures.append(f'{template_id}/{fmt}: falta color {color_key} {color}')

        if f'data-template-id="{template_id}"' not in lowered:
            failures.append(f'{template_id}/{fmt}: falta data-template-id')
        if fmt == 'pdf' and template_id not in lowered:
            failures.append(f'{template_id}/pdf: falta identidad de template')

        self._check_no_base_color_leak(template_id, fmt, lowered, colors, failures)

    def _check_no_base_color_leak(self, template_id, fmt, lowered, own_colors, failures):
        base_template_id = BASE_LAYOUT_BY_TEMPLATE.get(template_id)
        if not base_template_id or base_template_id == template_id:
            return
        base_contract = get_template_contract(base_template_id)
        if not base_contract:
            return

        own_values = {str(value).lower() for value in (own_colors or {}).values() if value}
        base_colors = base_contract.get('colors') or {}
        for color_key, color_value in base_colors.items():
            color = str(color_value or '').lower()
            if color and color not in own_values and color in lowered:
                failures.append(
                    f'{template_id}/{fmt}: color filtrado de base {base_template_id} '
                    f'({color_key} {color})'
                )

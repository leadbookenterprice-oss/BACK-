import json
import os

from django.core.management.base import BaseCommand, CommandError

from api.models import APIKey, Servicio
from api.services.pool_service import SERVICE_DEFAULTS


class Command(BaseCommand):
    help = 'Carga cuentas API al pool desde JSON en API_POOL_JSON, sin credenciales hardcodeadas.'

    def handle(self, *args, **kwargs):
        raw_pool = os.environ.get('API_POOL_JSON', '')
        if not raw_pool:
            raise CommandError('Defini API_POOL_JSON con una lista JSON de credenciales para cargar el pool.')

        try:
            cuentas = json.loads(raw_pool)
        except json.JSONDecodeError as exc:
            raise CommandError(f'API_POOL_JSON no es JSON valido: {exc}') from exc

        if not isinstance(cuentas, list):
            raise CommandError('API_POOL_JSON debe ser una lista de objetos.')

        creadas = 0
        existentes = 0
        for cuenta in cuentas:
            if not isinstance(cuenta, dict):
                raise CommandError('Cada item de API_POOL_JSON debe ser un objeto.')
            servicio_nombre = str(cuenta.get('servicio') or '').strip().lower()
            api_key = str(cuenta.get('api_key') or '').strip()
            if not servicio_nombre or not api_key:
                raise CommandError('Cada cuenta requiere servicio y api_key.')

            defaults = SERVICE_DEFAULTS.get(servicio_nombre, {})
            servicio, _ = Servicio.objects.update_or_create(
                nombre=servicio_nombre,
                defaults={
                    'descripcion': defaults.get('descripcion', servicio_nombre.title()),
                    'activo': True,
                    'default_daily_limit': defaults.get('default_daily_limit', 1500),
                    'default_monthly_limit': defaults.get('default_monthly_limit'),
                    'extra_increment': defaults.get('extra_increment', 1500),
                },
            )
            _, created = APIKey.objects.get_or_create(
                servicio=servicio,
                api_key=api_key,
                defaults={
                    'label': cuenta.get('label') or f'{servicio_nombre}-pool',
                    'status': 'available',
                    'google_daily_limit': int(cuenta.get('daily_limit') or defaults.get('default_daily_limit') or 1500),
                },
            )
            if created:
                creadas += 1
            else:
                existentes += 1

        self.stdout.write(self.style.SUCCESS(f'Pool cargado: {creadas} creadas, {existentes} existentes'))

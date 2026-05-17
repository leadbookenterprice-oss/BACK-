import json
import os

from django.core.management.base import BaseCommand, CommandError

from api.models import APIKey, Servicio


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

            servicio, _ = Servicio.objects.get_or_create(nombre=servicio_nombre)
            _, created = APIKey.objects.get_or_create(servicio=servicio, api_key=api_key)
            if created:
                creadas += 1
            else:
                existentes += 1

        self.stdout.write(self.style.SUCCESS(f'Pool cargado: {creadas} creadas, {existentes} existentes'))

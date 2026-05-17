from django.core.management.base import BaseCommand

from api.models import Agent
from api.services.pool_service import APIPoolService


class Command(BaseCommand):
    help = 'Repara usuarios free con APIs faltantes usando el schema actual de asignaciones'

    def handle(self, *args, **kwargs):
        users = Agent.objects.filter(plan_nombre='free')
        fixed = 0
        self.stdout.write(self.style.SUCCESS(f'Iniciando revisión de {users.count()} usuarios free...'))

        for user in users:
            repaired = APIPoolService.repair_user_apis(user)
            if repaired:
                fixed += 1
                self.stdout.write(self.style.SUCCESS(f"Usuario {user.email} reparado: {', '.join(repaired)}."))
            else:
                self.stdout.write(f'Usuario {user.email} no requirió reparación o no hay stock.')

        self.stdout.write(self.style.SUCCESS(f'Finalizado. Usuarios reparados: {fixed}'))

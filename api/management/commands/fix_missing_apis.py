from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Agent, APIKey, APIBundleAssignment

class Command(BaseCommand):
    help = 'Repara los usuarios del plan free que tienen menos de 3 APIs asignadas'

    def handle(self, *args, **kwargs):
        users = Agent.objects.filter(plan='free')
        fixed = 0
        self.stdout.write(self.style.SUCCESS(f'Iniciando revisión de {users.count()} usuarios free...'))
        
        for user in users:
            # Check si tiene un bundle activo completo
            bundle_assignment = APIBundleAssignment.objects.filter(usuario=user, activo=True).first()
            if bundle_assignment and bundle_assignment.bundle.is_complete():
                continue
                
            # Si no, verificamos sus keys individuales heredadas
            keys = APIKey.objects.filter(assigned_to=user)
            if keys.count() >= 3:
                continue
                
            self.stdout.write(self.style.WARNING(f'Usuario {user.email} (ID: {user.id}) tiene {keys.count()} APIs. Intentando reparar...'))
            
            # Verificamos cuáles servicios tiene y cuáles faltan
            owned_services = list(keys.values_list('servicio', flat=True))
            missing_services = [s for s in ['gemini', 'elevenlabs', 'uploadpost'] if s not in owned_services]
            
            success = True
            for s in missing_services:
                key = APIKey.objects.filter(status='available', servicio=s).first()
                if key:
                    key.status = 'assigned'
                    key.assigned_to = user
                    key.assigned_at = timezone.now()
                    key.save()
                    self.stdout.write(self.style.SUCCESS(f'  [+] Asignada API de {s} exitosamente.'))
                else:
                    self.stdout.write(self.style.ERROR(f'  [-] FALLO: No hay APIs disponibles en el pool para {s}.'))
                    success = False
                    
            if success:
                fixed += 1
                self.stdout.write(self.style.SUCCESS(f'Usuario {user.email} reparado correctamente (3 APIs completas).\n'))
            else:
                self.stdout.write(self.style.ERROR(f'Usuario {user.email} sigue incompleto por falta de stock.\n'))
                
        self.stdout.write(self.style.SUCCESS(f'Finalizado. Usuarios reparados: {fixed}'))

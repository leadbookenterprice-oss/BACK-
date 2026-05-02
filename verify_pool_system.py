import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, APIKey
from api.services.pool_service import APIPoolService

def run_verify():
    print("Iniciando verificación del Pool System...")
    
    # 1. Crear usuario de prueba
    email = "test_pool@leadbook.local"
    user, created = Agent.objects.get_or_create(email=email, defaults={'nombre': 'Test Pool', 'plan_nombre': 'free'})
    if created:
        print(f"Usuario {email} creado.")
    else:
        print(f"Usuario {email} ya existe.")
        APIPoolService.release_keys_from_user(user) # Limpiar para el test
        
    # 2. Asignar keys manualmente (simulando post_save)
    asignadas = APIPoolService.assign_keys_to_user(user)
    print(f"Keys asignadas: {asignadas}")
    
    keys_usuario = APIKey.objects.filter(assigned_to=user)
    print(f"Total keys vinculadas al usuario: {keys_usuario.count()}")
    for k in keys_usuario:
        print(f" - {k.servicio}: {k.status}")
        
    print("\nVerificación de Estadísticas:")
    print(APIPoolService.get_pool_stats())
    
    # Limpieza
    if created:
        user.delete()
        print("Usuario de test eliminado.")
        
if __name__ == '__main__':
    run_verify()

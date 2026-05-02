import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from django.db import connection
from django.conf import settings

# --- SAFETY LOCK ---
# Prevent running in production or if connected to Railway DB
if os.environ.get('RAILWAY_ENVIRONMENT') or 'railway' in getattr(settings, 'DATABASES', {}).get('default', {}).get('HOST', ''):
    print("❌ ERROR: ESTÁS CONECTADO A LA BASE DE DATOS DE PRODUCCIÓN (RAILWAY).")
    print("Por seguridad, este script ha sido bloqueado para evitar borrar los datos reales.")
    sys.exit(1)

confirmation = input("⚠️ ATENCIÓN: Este script borrará TODOS los datos de tu base de datos local. Escribe 'BORRAR TODO' para continuar: ")
if confirmation != "BORRAR TODO":
    print("Operación cancelada.")
    sys.exit(0)

print("Dropping public schema...")
with connection.cursor() as cursor:
    cursor.execute("DROP SCHEMA public CASCADE;")
    cursor.execute("CREATE SCHEMA public;")
print("Public schema dropped and recreated successfully. You can now run migrations.")

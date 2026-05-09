import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

with connection.cursor() as cursor:
    print("Limpiando historial de migraciones de 'api'...")
    cursor.execute("DELETE FROM django_migrations WHERE app = 'api';")
    print("Historial limpio.")

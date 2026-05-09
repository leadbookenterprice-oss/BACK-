import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

with connection.cursor() as cursor:
    print("Obteniendo tablas 'api_*'...")
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'api_%%';")
    tables = [t[0] for t in cursor.fetchall()]
    
    for t in tables:
        print(f"Borrando tabla {t}...")
        cursor.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
    
    print("Limpiando historial de migraciones...")
    cursor.execute("DELETE FROM django_migrations;")
    
    print("Purga completa.")

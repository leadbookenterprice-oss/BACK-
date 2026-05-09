import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

with connection.cursor() as cursor:
    print("Obteniendo TODAS las tablas del esquema 'public'...")
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    tables = [t[0] for t in cursor.fetchall()]
    
    for t in tables:
        print(f"Borrando tabla {t}...")
        cursor.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
    
    print("Borrando tipos custom (si existen)...")
    # A veces hay enums o tipos personalizados que pueden molestar
    
    print("Purga TOTAL completa.")

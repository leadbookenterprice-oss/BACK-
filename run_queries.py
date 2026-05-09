import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()
from django.db import connection

def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

with connection.cursor() as cursor:
    print("--- Estado real del usuario 6 (api_userapiquota) ---")
    cursor.execute("""
        SELECT service, daily_limit, monthly_limit, requests_today, is_blocked 
        FROM api_userapiquota 
        WHERE user_id = 6;
    """)
    rows1 = dictfetchall(cursor)
    for row in rows1:
        print(row)
        
    print("\n--- APIs extra asignadas al usuario 6 (api_bundleapiextra) ---")
    cursor.execute("""
        SELECT id, servicio, activa, pago_id, comprada_en, api_key_id
        FROM api_bundleapiextra 
        WHERE usuario_id = 6;
    """)
    rows2 = dictfetchall(cursor)
    for row in rows2:
        print(row)

    print("\n--- APIKey de Gemini asignada al usuario 6 (api_apikey) ---")
    cursor.execute("""
        SELECT id, servicio, status, api_key, daily_limit, requests_today, assigned_to_id
        FROM api_apikey 
        WHERE assigned_to_id = 6;
    """)
    rows3 = dictfetchall(cursor)
    for row in rows3:
        print(row)

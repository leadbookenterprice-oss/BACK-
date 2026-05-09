import psycopg2
import os

DATABASE_URL = "postgresql://postgres:plsOyadKzrwUCjDtNhWllVyhUMzUwoci@shinkansen.proxy.rlwy.net:37371/railway"

def print_results(cursor, title):
    print(f"\n--- {title} ---")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    if not rows:
        print("(Cero resultados)")
    for row in rows:
        row_dict = dict(zip(columns, row))
        print(row_dict)

try:
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT service, daily_limit, monthly_limit, requests_today, is_blocked 
            FROM api_userapiquota 
            WHERE user_id = 6;
        """)
        print_results(cur, "Estado real del usuario 6 (api_userapiquota)")
        
        cur.execute("""
            SELECT id, servicio, activa, pago_id, comprada_en, api_key_id
            FROM api_bundleapiextra 
            WHERE usuario_id = 6;
        """)
        print_results(cur, "APIs extra asignadas al usuario 6 (api_bundleapiextra)")
        
        cur.execute("""
            SELECT id, servicio, status, api_key, daily_limit, requests_today, assigned_to_id
            FROM api_apikey 
            WHERE assigned_to_id = 6;
        """)
        print_results(cur, "APIKey de Gemini asignada al usuario 6 (api_apikey)")
except Exception as e:
    print("Error:", e)
finally:
    if 'conn' in locals() and conn:
        conn.close()

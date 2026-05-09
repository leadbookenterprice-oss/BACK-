import psycopg2, json
from datetime import datetime, date

DATABASE_URL = "postgresql://postgres:plsOyadKzrwUCjDtNhWllVyhUMzUwoci@shinkansen.proxy.rlwy.net:37371/railway"

def safe_str(v):
    if v is None: return "NULL"
    if isinstance(v, (datetime, date)): return str(v)
    return str(v)

def run(cur, title, sql):
    print(f"\n=== {title} ===")
    cur.execute(sql)
    if not cur.description:
        print("(no rows)")
        return
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(" | ".join(cols))
    print("-" * 100)
    for row in rows:
        print(" | ".join(safe_str(v) for v in row))
    print(f"[{len(rows)} rows]")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

run(cur, "Q1 - Todas las tablas",
    "SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;")

run(cur, "Q2 - Estructura columnas api_*",
    "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name LIKE 'api_%' ORDER BY table_name, ordinal_position;")

run(cur, "Q3 - Foreign keys api_*",
    """SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_name LIKE 'api_%'
ORDER BY tc.table_name;""")

for tbl in ["api_apikey","api_userapiquota","api_bundleapiextra","api_apibundle","api_apibundleassignment"]:
    run(cur, f"Q4 - {tbl} LIMIT 5", f"SELECT * FROM {tbl} LIMIT 5;")

cur.close()
conn.close()

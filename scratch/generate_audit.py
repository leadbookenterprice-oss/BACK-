import os
import psycopg2

DATABASE_URL = "postgresql://postgres:plsOyadKzrwUCjDtNhWllVyhUMzUwoci@shinkansen.proxy.rlwy.net:37371/railway"

FILES_TO_INCLUDE = [
    "api/models.py",
    "api/urls.py",
    "api/views.py",
    "api/views_admin.py",
    "api/serializers.py",
    "api/tasks.py",
    "subzero_core/settings.py"
]

def search_files(keyword, root_dir="."):
    matches = set()
    for dirpath, _, filenames in os.walk(root_dir):
        if 'venv' in dirpath or '__pycache__' in dirpath or '.git' in dirpath:
            continue
        for f in filenames:
            if not f.endswith('.py'):
                continue
            path = os.path.join(dirpath, f)
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    if keyword in file.read():
                        matches.add(path)
            except Exception:
                pass
    return matches

def run_query(cursor, query):
    try:
        cursor.execute(query)
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return columns, rows
        return [], []
    except Exception as e:
        return ["Error"], [[str(e)]]

def format_table(columns, rows):
    if not columns:
        return "(Sin resultados)\n"
    
    col_widths = [max(len(str(item)) for item in col) for col in zip(*rows, columns)] if rows else [len(c) for c in columns]
    
    header = " | ".join(str(c).ljust(w) for c, w in zip(columns, col_widths))
    separator = "-+-".join("-" * w for w in col_widths)
    
    res = [header, separator]
    for row in rows:
        res.append(" | ".join(str(item).ljust(w) for item, w in zip(row, col_widths)))
    return "\n".join(res) + "\n"

def main():
    out_file = "project_audit.md"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("# COMPLETE LEADBOOK PROJECT AUDIT\n\n")
        
        # 1. SQL QUERIES
        f.write("## DATABASE AUDIT (Production)\n\n")
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                queries = [
                    ("SQL QUERY 1 - Todas las tablas", "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"),
                    ("SQL QUERY 2 - Estructura completa de todas las tablas", "SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name LIKE 'api_%' ORDER BY table_name, ordinal_position;"),
                    ("SQL QUERY 3 - Todas las relaciones entre tablas", "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name LIKE 'api_%' ORDER BY tc.table_name;"),
                    ("SQL QUERY 4.1 - Datos api_apikey (limit 5)", "SELECT * FROM api_apikey LIMIT 5;"),
                    ("SQL QUERY 4.2 - Datos api_userapiquota (limit 5)", "SELECT * FROM api_userapiquota LIMIT 5;"),
                    ("SQL QUERY 4.3 - Datos api_bundleapiextra (limit 5)", "SELECT * FROM api_bundleapiextra LIMIT 5;"),
                    ("SQL QUERY 4.4 - Datos api_apibundle (limit 5)", "SELECT * FROM api_apibundle LIMIT 5;"),
                    ("SQL QUERY 4.5 - Datos api_apibundleassignment (limit 5)", "SELECT * FROM api_apibundleassignment LIMIT 5;"),
                    ("SQL QUERY 4.6 - Datos api_suscripcion (limit 5)", "SELECT * FROM api_suscripcion LIMIT 5;"),
                ]
                
                for title, sql in queries:
                    f.write(f"### {title}\n")
                    f.write(f"```sql\n{sql}\n```\n")
                    cols, rows = run_query(cur, sql)
                    f.write("```text\n")
                    f.write(format_table(cols, rows))
                    f.write("```\n\n")
                    
        except Exception as e:
            f.write(f"**Database Connection Error:** {e}\n\n")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

        # 2. FILE SEARCH FOR MERCADOPAGO / WEBHOOK
        f.write("## FILES CONTAINING 'mercadopago' OR 'webhook'\n\n")
        extra_files = search_files("mercadopago").union(search_files("webhook"))
        
        all_files_to_read = set(FILES_TO_INCLUDE).union(extra_files)
        
        # 3. SOURCE CODE
        f.write("## SOURCE CODE\n\n")
        for filepath in sorted(list(all_files_to_read)):
            f.write(f"### File: {filepath}\n")
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as src:
                    content = src.read()
                f.write(f"```python\n{content}\n```\n\n")
            else:
                f.write(f"*(File does not exist)*\n\n")

if __name__ == "__main__":
    main()

import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, api_key FROM api_apikey WHERE servicio='cloudinary'")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} Cloudinary keys:")
    for row in rows:
        print(f"ID: {row[0]}, Key: {row[1][:50]}...")
except Exception as e:
    print(f"Error: {e}")

conn.close()

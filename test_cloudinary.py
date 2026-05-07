import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.services.almacenamiento import AlmacenamientoCloudinary

# Test 1: Ver si encuentra las cuentas del pool
creds, key_id = AlmacenamientoCloudinary.get_mejor_cuenta()
print(f"Cuenta encontrada: {creds}")
print(f"Key ID: {key_id}")

# Test 2: Subir una imagen de prueba
import requests
img = requests.get("https://via.placeholder.com/300x200.jpg").content
import cloudinary
import cloudinary.uploader
if creds:
    cloudinary.config(
        cloud_name=creds['cloud_name'],
        api_key=creds['api_key'],
        api_secret=creds['api_secret']
    )
    result = cloudinary.uploader.upload(img, public_id="test/prueba_leadbook")
    print(f"✅ Subida exitosa: {result['secure_url']}")
else:
    print("❌ No se encontró ninguna cuenta en el pool")

import os
import sys
import django

# Añadir el directorio actual al path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import APIKey

keys = APIKey.objects.filter(servicio='cloudinary')
print(f"Found {len(keys)} Cloudinary keys:")
for k in keys:
    print(f"ID: {k.id}, Status: {k.status}, Key: {k.api_key[:50]}...")

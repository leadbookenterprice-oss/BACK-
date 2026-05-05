import os
import sys
import django
import cloudinary

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

print(f"Cloud Name: {cloudinary.config().cloud_name}")
print(f"API Key: {cloudinary.config().api_key}")
print(f"API Secret: {'*' * len(cloudinary.config().api_secret) if cloudinary.config().api_secret else 'EMPTY'}")

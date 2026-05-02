import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

import cloudinary.uploader
try:
    result = cloudinary.uploader.upload('https://raw.githubusercontent.com/github/explore/main/topics/django/django.png', folder='leadbook/test')
    print('✅ Funciona:', result['secure_url'])
except Exception as e:
    print('❌ Error:', str(e))

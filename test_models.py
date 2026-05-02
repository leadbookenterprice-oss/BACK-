import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
import django
django.setup()

import google.generativeai as genai
from django.conf import settings
genai.configure(api_key=settings.GEMINI_API_KEY)
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)

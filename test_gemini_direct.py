import os
import django
import sys

# Setup django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.ai_services import call_gemini_api

try:
    print("Testing Gemini...")
    res = call_gemini_api('Hola, respondé solo con OK')
    print('GEMINI_OK:', res)
except Exception as e:
    print('GEMINI_ERROR:', str(e))

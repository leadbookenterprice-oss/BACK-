import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
import django; django.setup()
from api.ai_services import call_gemini_api, call_groq_api
import time

# Test Gemini
print("=== TEST GEMINI ===")
t0 = time.time()
try:
    res = call_gemini_api('Responde solo la palabra: OK')
    print('GEMINI OK:', repr(res))
    print('Tiempo:', round(time.time()-t0, 2), 's')
except Exception as e:
    print('GEMINI FAIL:', type(e).__name__)
    print('Error:', str(e)[:300])

# Test Groq
print("\n=== TEST GROQ ===")
t0 = time.time()
try:
    res = call_groq_api('Responde solo la palabra: OK')
    print('GROQ OK:', repr(res))
    print('Tiempo:', round(time.time()-t0, 2), 's')
except Exception as e:
    print('GROQ FAIL:', type(e).__name__)
    print('Error:', str(e)[:300])

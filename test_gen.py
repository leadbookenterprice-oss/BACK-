import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
import django
django.setup()

from api.ai_services import call_gemini_api
try:
    print(call_gemini_api("Hola", system_prompt="Sos un test."))
except Exception as e:
    import traceback
    with open('err.log', 'w') as f:
        traceback.print_exc(file=f)
    print("Error written to err.log")

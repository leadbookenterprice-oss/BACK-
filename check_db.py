import os
import django
import sys

# Agrega la ruta actual
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.pool_manager import get_api_key
from api.models import APIBundleAssignment, APIKey

User = get_user_model()
try:
    user = User.objects.get(email='byte.business.hub@gmail.com')
    print(f"User plan: {user.plan_nombre}")
    key = get_api_key(user, 'gemini')
    print(f"Key from pool_manager: {key}")
    
    asig = APIBundleAssignment.objects.filter(usuario=user, activo=True).first()
    if asig:
        print(f"Bundle assigned: {asig.bundle.name if hasattr(asig.bundle, 'name') else asig.bundle.id}")
        if asig.bundle.key_gemini:
            print(f"Gemini key in bundle: {asig.bundle.key_gemini.api_key}")
        else:
            print("No Gemini key in bundle")
    else:
        print("No active bundle assigned")
        
    legacy = APIKey.objects.filter(assigned_to=user, servicio='gemini').first()
    if legacy:
        print(f"Legacy key: {legacy.api_key}")
    else:
        print("No legacy key assigned")
except Exception as e:
    print('Error:', e)

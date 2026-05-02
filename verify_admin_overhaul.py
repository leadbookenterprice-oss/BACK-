import os
import django
import sys

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, APIKey
from django.utils.timezone import now

def verify_admin_system():
    print("Verifying Admin System...")
    
    # 1. Check Agent model for eliminado_en
    has_field = hasattr(Agent, 'eliminado_en')
    print(f"Agent has 'eliminado_en' field: {has_field}")
    
    # 2. Check if we can create a dummy user and soft delete it
    try:
        user, created = Agent.objects.get_or_create(email="test_admin_delete@example.com", defaults={"nombre": "Test Delete"})
        user.is_active = True
        user.eliminado_en = None
        user.save()
        
        print(f"Test user created: {user.email}")
        
        # Simulate soft delete
        user.is_active = False
        user.eliminado_en = now()
        user.save()
        print("Soft delete simulated.")
        
        # Verify
        reloaded = Agent.objects.get(id=user.id)
        print(f"User is_active: {reloaded.is_active}, eliminado_en: {reloaded.eliminado_en}")
        
        # Cleanup
        reloaded.delete()
        print("Test user cleaned up.")
    except Exception as e:
        print(f"Error during user verification: {e}")

    # 3. Check APIKey pool
    try:
        keys_count = APIKey.objects.count()
        print(f"APIKey count: {keys_count}")
    except Exception as e:
        print(f"Error during APIKey verification: {e}")

    print("Verification finished.")

if __name__ == "__main__":
    verify_admin_system()

import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

def test_endpoints():
    print("=== TAREA 4: INTEGRATION TESTS ===")
    
    # Login
    login_url = f"{BASE_URL}/api/auth/login/"
    login_data = {"email": "Charlyadmin@gmail.com", "password": "Elcharlesx143"}
    try:
        r = requests.post(login_url, json=login_data)
        if r.status_code != 200:
            print(f"FAILED LOGIN: {r.status_code} - {r.text}")
            return
        token = r.json().get('access')
        print("✅ Login exitoso")
    except Exception as e:
        print(f"ERROR LOGIN: {e}")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Perfil
    print("\n--- Perfil ---")
    r = requests.get(f"{BASE_URL}/api/auth/perfil/", headers=headers)
    print(json.dumps(r.json(), indent=2))

    # Plan Status
    print("\n--- Plan Status ---")
    r = requests.get(f"{BASE_URL}/api/auth/plan-status/", headers=headers)
    print(json.dumps(r.json(), indent=2))

    # Dashboard
    print("\n--- Dashboard ---")
    r = requests.get(f"{BASE_URL}/api/dashboard/", headers=headers)
    print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    test_endpoints()

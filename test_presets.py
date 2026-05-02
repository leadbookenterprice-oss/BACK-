import requests, json
login = requests.post('http://127.0.0.1:8001/api/auth/login/', 
  json={'email': 'charlysanmartin20@gmail.com', 'password': 'test123'})

if login.status_code != 200:
    print('LOGIN FAILED:', login.status_code, login.text)
else:
    token = login.json().get('access')
    h = {'Authorization': 'Bearer ' + token}

    # Guardar preset
    r1 = requests.post('http://127.0.0.1:8001/api/amenidades-presets/', 
      json={'nombre': 'Vista al mar'}, headers=h)
    print('GUARDAR:', r1.status_code, r1.json())

    # Listar presets
    r2 = requests.get('http://127.0.0.1:8001/api/amenidades-presets/', 
      headers=h)
    print('LISTAR:', r2.status_code, r2.json())

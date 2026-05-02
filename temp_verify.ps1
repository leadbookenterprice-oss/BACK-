Write-Host "VERIFICACION 1..."
try {
  $token = (Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login/" -Method Post -Body '{"email":"Charlyadmin@gmail.com","password":"Elcharlesx143"}' -ContentType "application/json").access
  $headers = @{"Authorization"="Bearer $token"}
  Write-Host "Login: OK"
} catch {
  Write-Host "Login Error: $_"
}

if ($headers) {
  Write-Host "`n# Onboarding"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/onboarding/" -Method Put -Headers $headers -Body '{"nombre_inmobiliaria":"Test","nicho":"inmobiliaria","pais":"Argentina"}' -ContentType "application/json" | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Perfil"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/perfil/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Dashboard"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/dashboard/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Admin metricas"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/metricas/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Admin usuarios"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/usuarios/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Instagram service"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/publicar-instagram/" -Method Post -Headers $headers -Body '{"imagen_url":"http://test.com/img.jpg","caption":"test","tipo":"post"}' -ContentType "application/json" | Format-List } catch { Write-Host "Error: $_" }

  Write-Host "`n# Video status"
  try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/video-status/1/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }
}

Write-Host "`n=== VERIFICACION 3 ==="
if (Test-Path "video_engine") { cd video_engine; npm list --depth=0; cd .. } else { Write-Host "No video_engine directory" }

Write-Host "`n=== VERIFICACION 5 ==="
if (Test-Path ".\venv\Scripts\python.exe") {
    .\venv\Scripts\python manage.py shell -c "from api.models import Agent; print(Agent.objects.filter(is_staff=True).values('email','is_staff'))"
} else {
    Write-Host "Python in venv not found."
}

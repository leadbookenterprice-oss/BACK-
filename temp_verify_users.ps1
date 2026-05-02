function Test-Login {
    param($email, $password)
    Write-Host "`n=== Probando con $email ==="
    try {
        $token = (Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login/" -Method Post -Body (@{email=$email; password=$password} | ConvertTo-Json) -ContentType "application/json").access
        $headers = @{"Authorization"="Bearer $token"}
        Write-Host "Login: OK"
        
        Write-Host "`n# Onboarding:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/onboarding/" -Method Put -Headers $headers -Body '{"nombre_inmobiliaria":"Test","nicho":"inmobiliaria","pais":"Argentina"}' -ContentType "application/json" | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Perfil:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/perfil/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Dashboard:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/dashboard/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Admin metricas:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/metricas/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Admin usuarios:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/usuarios/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Instagram service:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/publicar-instagram/" -Method Post -Headers $headers -Body '{"imagen_url":"http://test.com/img.jpg","caption":"test","tipo":"post"}' -ContentType "application/json" | Format-List } catch { Write-Host "Error: $_" }

        Write-Host "`n# Video status:"
        try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/video-status/1/" -Method Get -Headers $headers | Format-List } catch { Write-Host "Error: $_" }
    } catch {
        Write-Host "Login fail: $_"
    }
}

Test-Login 'Charlyadmin@gmail.com' 'Elcharlesx143'
Test-Login 'Atilioadmin@gmail.com' 'Atiliusx4321'

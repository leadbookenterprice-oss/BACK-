$baseUrl = "http://localhost:8000"

# 1. Login como admin
Write-Host "=== 1. Login como admin@leadbook.io ==="
$loginData = @{ email = "admin@leadbook.io"; password = "LeadBook2025!" }
$loginResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/login/" -Body ($loginData | ConvertTo-Json) -ContentType "application/json"
$token = $loginResp.access
$headers = @{ "Authorization" = "Bearer $token" }
Write-Host "Token OK"

# 2. Metricas
Write-Host "`n=== 2. GET /api/admin/metricas/ ==="
$metricas = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/admin/metricas/" -Headers $headers
$metricas | ConvertTo-Json -Depth 5 | Write-Host

# 3. Lista de usuarios
Write-Host "`n=== 3. GET /api/admin/usuarios/ ==="
$usuarios = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/admin/usuarios/" -Headers $headers
Write-Host "Total usuarios: $($usuarios.total)"
$usuarios.usuarios | Select-Object id, email, plan, listados_totales | Format-Table | Out-String | Write-Host

# 4. Registrar usuario de prueba para cambiar plan
Write-Host "=== 4. Registrar usuario de prueba ==="
$regData = @{ email = "plan_test@test.com"; nombre = "Plan Tester"; password = "password123" }
try {
    $regResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/register/" -Body ($regData | ConvertTo-Json) -ContentType "application/json"
    $testUserId = $null
    # Buscar su ID
    $usuarios2 = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/admin/usuarios/" -Headers $headers
    $testUser = $usuarios2.usuarios | Where-Object { $_.email -eq "plan_test@test.com" }
    $testUserId = $testUser.id
    Write-Host "Usuario de prueba ID: $testUserId"
} catch {
    Write-Host "Ya existe, buscando ID..."
    $usuarios2 = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/admin/usuarios/" -Headers $headers
    $testUser = $usuarios2.usuarios | Where-Object { $_.email -eq "plan_test@test.com" }
    $testUserId = $testUser.id
    Write-Host "ID: $testUserId"
}

# 5. Cambiar plan
Write-Host "`n=== 5. PUT /api/admin/usuarios/$testUserId/plan/ ==="
$planData = @{ plan = "pro" }
$planResp = Invoke-RestMethod -Method Put -Uri "$baseUrl/api/admin/usuarios/$testUserId/plan/" -Body ($planData | ConvertTo-Json) -ContentType "application/json" -Headers $headers
$planResp | ConvertTo-Json | Write-Host

# 6. Eliminar usuario de prueba
Write-Host "`n=== 6. DELETE /api/admin/usuarios/$testUserId/ ==="
try {
    $delResp = Invoke-RestMethod -Method Delete -Uri "$baseUrl/api/admin/usuarios/$testUserId/" -Headers $headers
    $delResp | ConvertTo-Json | Write-Host
} catch {
    $streamReader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    Write-Host $streamReader.ReadToEnd()
}

# 7. Probar acceso denegado con usuario normal
Write-Host "`n=== 7. Verificar 403 con usuario normal ==="
$normalLogin = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/login/" -Body (@{ email = "testig_ps1@test.com"; password = "password123" } | ConvertTo-Json) -ContentType "application/json"
$normalHeaders = @{ "Authorization" = "Bearer $($normalLogin.access)" }
try {
    Invoke-RestMethod -Method Get -Uri "$baseUrl/api/admin/metricas/" -Headers $normalHeaders
} catch {
    $streamReader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    $errBody = $streamReader.ReadToEnd() | ConvertFrom-Json
    Write-Host "403 OK - Error: $($errBody.error)"
}

Write-Host "`n=== Todos los endpoints admin verificados ==="

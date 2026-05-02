$baseUrl = "http://localhost:8000"

# Register a temporary user
$registerData = @{
    email = "testonboarding_ps1@test.com"
    nombre = "Test Agent PS"
    password = "password123"
}

Write-Host "--- 1. Registering User ---"
$regResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/register/" -Body ($registerData | ConvertTo-Json) -ContentType "application/json"
$token = $regResponse.access
Write-Host "Token received.`n"

# Onboarding
$onboardingData = @{
    nombre_inmobiliaria = "Inmobiliaria Estrella"
    logo_url = "data:image/png;base64,mocked"
    nicho = "inmobiliaria"
    pais = "Argentina"
}

$headers = @{
    "Authorization" = "Bearer $token"
}

Write-Host "--- 2. Haciendo Onboarding (PUT /api/auth/onboarding/) ---"
$onbResponse = Invoke-RestMethod -Method Put -Uri "$baseUrl/api/auth/onboarding/" -Body ($onboardingData | ConvertTo-Json) -ContentType "application/json" -Headers $headers

$onbResponse | ConvertTo-Json -Depth 5 | Write-Host
Write-Host "`n"

Write-Host "--- 3. Verificando Perfil (GET /api/auth/perfil/) ---"
$perfilResponse = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/auth/perfil/" -Headers $headers

$perfilResponse | ConvertTo-Json -Depth 5 | Write-Host

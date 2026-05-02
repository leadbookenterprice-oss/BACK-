$baseUrl = "http://localhost:8000"

# Register a temporary user
$registerData = @{
    email = "testig_ps1@test.com"
    nombre = "Test Agent IG"
    password = "password123"
}

Write-Host "--- 1. Registering User ---"
$regResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/auth/register/" -Body ($registerData | ConvertTo-Json) -ContentType "application/json"
$token = $regResponse.access
$headers = @{
    "Authorization" = "Bearer $token"
}

Write-Host "`n--- 2. Probando sin tener configurado Token de FB ---"
$postData = @{
    tipo = "post"
    imagen_url = "https://via.placeholder.com/300"
    caption = "Testeo desde PowerShell"
}
try {
    $resFail = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/publicar-instagram/" -Body ($postData | ConvertTo-Json) -ContentType "application/json" -Headers $headers
} catch {
    $streamReader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    $ErrResp = $streamReader.ReadToEnd() | ConvertFrom-Json
    Write-Host "Expected Error: $($ErrResp.error)"
}

Write-Host "`n--- 3. Guardando credenciales de FB Falsas usando PerfilView ---"
$perfilData = @{
    meta_access_token = "dummy_token_fb_123"
    meta_instagram_account_id = "dummy_account_id_321"
}
$resPerfil = Invoke-RestMethod -Method Put -Uri "$baseUrl/api/auth/perfil/" -Body ($perfilData | ConvertTo-Json) -ContentType "application/json" -Headers $headers
Write-Host "Credenciales actualizadas en: $($resPerfil.email) con Token: $($resPerfil.meta_access_token)"

Write-Host "`n--- 4. Publicando POST de prueba ---"
try {
    $resPost = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/publicar-instagram/" -Body ($postData | ConvertTo-Json) -ContentType "application/json" -Headers $headers
    $resPost | ConvertTo-Json -Depth 5 | Write-Host
} catch {
    $streamReader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
    $ErrResp = $streamReader.ReadToEnd() | ConvertFrom-Json
    Write-Host "Expected Meta Graph Error:"
    $ErrResp | ConvertTo-Json -Depth 5 | Write-Host
}

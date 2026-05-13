# Activa el entorno virtual del proyecto hotel_system
# Uso: . .\activate_env.ps1  (o: .\activate_env.ps1)
& "$PSScriptRoot\venv\Scripts\Activate.ps1"
Write-Host "✅ venv activado. Python: $(python --version)" -ForegroundColor Green

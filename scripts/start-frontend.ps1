$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $projectRoot 'frontend')
try {
    Write-Output 'Frontend: http://127.0.0.1:5175 (Java 8080 and Python 8000 must be running)'
    & node server.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Frontend failed to start. Check whether port 5175 is already in use.' }
} finally { Pop-Location }

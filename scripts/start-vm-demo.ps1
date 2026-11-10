$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    & ssh.exe -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=.local-run/vm-known-hosts root@192.168.100.128 'cd /opt/enterprise-support-agent/infra && docker compose up -d'
    if ($LASTEXITCODE -ne 0) { throw 'VM unavailable. Start the VMware VM and check SSH first.' }
    & "$PSScriptRoot/start-vm-tunnel.ps1"
    $shell = (Get-Command powershell.exe).Source
    foreach ($entry in @(
        @{Name='business';Port=8080;Script='.local-run/start-business.ps1'},
        @{Name='agent';Port=8000;Script='.local-run/start-agent.ps1'},
        @{Name='frontend';Port=5175;Script='scripts/start-frontend.ps1'}
    )) {
        if (Get-NetTCPConnection -State Listen -LocalPort $entry.Port -ErrorAction SilentlyContinue) {
            Write-Output "$($entry.Name): port $($entry.Port) is already listening; not starting another copy."
            continue
        }
        $script = Join-Path $projectRoot $entry.Script
        Start-Process -FilePath $shell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $script + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput "$projectRoot/.local-run/$($entry.Name)-launcher.out.log" -RedirectStandardError "$projectRoot/.local-run/$($entry.Name)-launcher.err.log" | Out-Null
    }
    $deadline = (Get-Date).AddSeconds(90)
    do {
        try {
            $javaHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/health' -TimeoutSec 3
            $agentHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 3
            $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5175/' -TimeoutSec 3
            if ($javaHealth.status -eq 'UP' -and $agentHealth.components.rag.status -eq 'UP' -and $agentHealth.components.redis.status -eq 'UP' -and $page.StatusCode -eq 200) {
                Write-Output 'Ready: http://127.0.0.1:5175 (Java, Agent, RAG and Redis are UP).'
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Startup did not become healthy within 90 seconds. Check .local-run/*-launcher.*.log.'
} finally { Pop-Location }

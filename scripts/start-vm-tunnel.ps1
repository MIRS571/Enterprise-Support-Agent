param([string]$VmHost = '192.168.100.128', [string]$VmUser = 'root')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runDir = Join-Path $projectRoot '.local-run'
$knownHosts = Join-Path $runDir 'vm-known-hosts'
if (!(Test-Path -LiteralPath $knownHosts)) { throw 'Missing verified VM host key. Complete the initial SSH setup first.' }
$ports = @(23306,25432,26379,26333)
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $ports })
if ($listeners.Count) {
    $owners = @($listeners.OwningProcess | Select-Object -Unique)
    if ($owners.Count -ne 1 -or @($listeners.LocalPort | Select-Object -Unique).Count -ne 4) { throw 'Some VM tunnel ports are already occupied; inspect them before restarting.' }
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
    if ($existing.Name -ne 'ssh.exe' -or $existing.CommandLine -notlike "*$VmUser@$VmHost*" -or $existing.CommandLine -notlike '*vm-known-hosts*') { throw 'Tunnel ports belong to another process.' }
    Write-Output 'Agent VM tunnel is already running.'
    return
}
$arguments = @('-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=.local-run/vm-known-hosts','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3')
foreach ($port in $ports) { $arguments += @('-L',"127.0.0.1:${port}:127.0.0.1:${port}") }
$arguments += "$VmUser@$VmHost"
$process = Start-Process -FilePath (Get-Command ssh.exe).Source -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $runDir 'vm-tunnel.err.log')
Start-Sleep -Seconds 1
if ($process.HasExited) { throw 'SSH tunnel failed. Check .local-run/vm-tunnel.err.log.' }
@{Id=$process.Id;Host=$VmHost;StartTime=$process.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $runDir 'vm-tunnel-process.json')
Write-Output 'Agent VM tunnel ready: MySQL 23306 / PostgreSQL 25432 / Redis 26379 / Qdrant 26333.'

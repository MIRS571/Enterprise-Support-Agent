$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$redisServer = Join-Path $projectRoot '.local-tools/redis/redis-server.exe'
$redisCli = Join-Path $projectRoot '.local-tools/redis/redis-cli.exe'
$data = Join-Path $projectRoot '.local-run/auth-redis'
if (!(Test-Path $redisServer)) { throw 'Redis runtime missing. See docs/authentication.md for Redis configuration.' }
if (Get-NetTCPConnection -LocalPort 16380 -State Listen -ErrorAction SilentlyContinue) {
    $reply = & $redisCli -h 127.0.0.1 -p 16380 ping
    if ($reply -ne 'PONG') { throw 'Port 16380 is occupied by another service.' }
    Write-Output 'Agent Redis already running on 127.0.0.1:16380'; return
}
New-Item -ItemType Directory -Force -Path $data | Out-Null
$dataPath = $data.Replace('\','/')
@"
bind 127.0.0.1
port 16380
protected-mode yes
appendonly yes
appendfsync always
save 60 1
maxmemory-policy noeviction
dir "$dataPath"
logfile "redis.log"
"@ | Set-Content -LiteralPath "$data/redis.conf" -Encoding ascii
Start-Process -FilePath $redisServer -ArgumentList ('"' + "$data/redis.conf" + '"') -WorkingDirectory $data -WindowStyle Hidden | Out-Null
Write-Output 'Agent Redis started on 127.0.0.1:16380'

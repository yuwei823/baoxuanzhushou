$ErrorActionPreference = 'Stop'
$Listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $Listeners) {
    Write-Host '8000 端口没有运行中的服务。'
    exit 0
}
foreach ($listener in $Listeners) {
    Write-Host "停止 PID $($listener.OwningProcess) ..."
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
}
Write-Host '服务已停止。'

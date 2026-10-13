# Push the local .env to the ECS instance.
#
# Run this from your Windows machine, in the project root:
#     .\scripts\push_env.ps1              # upload, then restart the service
#     .\scripts\push_env.ps1 -NoRestart   # upload only
#     .\scripts\push_env.ps1 -WhatIf      # show the diff, change nothing
#
# .env is gitignored, so it drifts silently: a key added locally never reaches
# the server, and the app falls back to code defaults. CI catches the drift
# against .env.example at deploy time; this script is how you fix it.
#
# The file is uploaded over SSH stdin, so the API key never lands in a temp
# file, a shell history, or a command line argument. The remote copy is backed
# up before being replaced.

param(
    [string]$Host_ = "47.80.242.151",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\baoxuan_deploy",
    [string]$RemoteDir = "/root/baoxuanzhushou",
    [string]$LocalEnv = "",
    [switch]$NoRestart,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

if (-not $LocalEnv) {
    $LocalEnv = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
}

if (-not (Test-Path $LocalEnv)) {
    Write-Error "Local .env not found: $LocalEnv"
}
if (-not (Test-Path $KeyPath)) {
    Write-Error "SSH key not found: $KeyPath"
}

# Read as bytes so the original encoding survives the round trip, and so a
# UTF-8 BOM is stripped rather than shipped into the first variable name.
$bytes = [System.IO.File]::ReadAllBytes($LocalEnv)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $bytes = $bytes[3..($bytes.Length - 1)]
}

# Normalize to LF. The remote file is parsed by `grep`/`cut` in the deploy
# workflow, and a stray CR would make a value compare unequal to .env.example.
$text = [System.Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"
$text = $text -replace "`r", "`n"
if (-not $text.EndsWith("`n")) { $text += "`n" }

$lines = $text -split "`n" | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' }
if ($lines.Count -eq 0) {
    Write-Error "No KEY=VALUE lines found in $LocalEnv"
}

$remoteEnv = "$RemoteDir/.env"
$target = "${User}@${Host_}"

Write-Host "Local  : $LocalEnv ($($lines.Count) variables)" -ForegroundColor Cyan
Write-Host "Remote : $remoteEnv on $target" -ForegroundColor Cyan

# Mask secrets in every line this script prints. The real values only ever
# travel inside the SSH stdin payload.
function Get-Masked([string]$line) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key, $value = $Matches[1], $Matches[2]
        if ($value.Length -eq 0) { return "$key=" }
        if ($key -match 'KEY|SECRET|TOKEN|PASSWORD') {
            return "$key=<set, $($value.Length) chars>"
        }
        return "$key=$value"
    }
    return $line
}

if ($WhatIf) {
    Write-Host "`n-WhatIf: the following would be written (secrets masked):`n" -ForegroundColor Yellow
    $lines | ForEach-Object { Get-Masked $_ }
    return
}

# The payload is embedded in the remote script rather than piped to it: the
# script is itself fed to bash over stdin, so a second consumer of stdin would
# race it. umask 077 keeps the key readable only by the owner. Keep the 5 most
# recent backups so a bad push can be reverted.
$envB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($text))
$remoteScript = @"
set -e
cd '$RemoteDir'
if [ -f .env ]; then
  cp .env ".env.bak-`$(date +%Y%m%d-%H%M%S)"
  ls -1t .env.bak-* | tail -n +6 | xargs -r rm --
  echo 'backed up previous .env'
else
  echo 'no previous .env; creating'
fi
umask 077
printf '%s' '$envB64' | base64 -d > .env
chmod 600 .env
echo "wrote `$(grep -c -E '^[A-Za-z_][A-Za-z0-9_]*=' .env) variables"
"@

# A multi-line here-string is re-split by the ssh client, so ship the remote
# script base64-encoded and decode it on the far side. The here-string carries
# CRLF on Windows, and a stray CR makes bash see `cd /path\r` and `set -`, so
# normalize to LF before encoding.
$remoteScript = $remoteScript -replace "`r`n", "`n" -replace "`r", "`n"
$remoteB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($remoteScript))
$remoteCmd = "echo '$remoteB64' | base64 -d | bash"

Write-Host ""
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new $target $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "Upload failed (ssh exit $LASTEXITCODE); remote .env left as-is"
}

if ($NoRestart) {
    Write-Host "`nUploaded. Restart skipped (-NoRestart); the running container still has the old values." -ForegroundColor Yellow
    return
}

# `up -d` recreates the container only when something changed, so this is safe
# to run when only the .env moved.
Write-Host "`nRecreating the audit service..." -ForegroundColor Cyan
$restart = "cd '$RemoteDir' && docker compose up -d --force-recreate audit && docker compose ps"
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new $target $restart
if ($LASTEXITCODE -ne 0) {
    Write-Error "Restart failed (ssh exit $LASTEXITCODE)"
}

Write-Host "`nDone. Verify with: .\scripts\show_remote_env.ps1" -ForegroundColor Green

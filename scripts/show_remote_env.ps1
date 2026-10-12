# Fetch the ECS .env for review, with the API key masked.
#
# Run this from your Windows machine, in the project root:
#     .\scripts\show_remote_env.ps1
#
# It prints the remote .env with DASHSCOPE_API_KEY replaced by a placeholder,
# so the output is safe to paste into a chat. Nothing is written to disk here.

param(
    [string]$Host_ = "47.80.242.151",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\baoxuan_deploy",
    [string]$RemoteEnv = "/root/baoxuanzhushou/.env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $KeyPath)) {
    Write-Error "SSH key not found: $KeyPath"
}

Write-Host "Reading $RemoteEnv on ${User}@${Host_} (API key will be masked)...`n" -ForegroundColor Cyan

# sed masks the secret on the remote side, so the real key never crosses the wire.
# Keep this a single line: a multi-line here-string is re-split by the ssh client.
$remote = "sed -E 's/^(DASHSCOPE_API_KEY=).*/\1<MASKED>/' '$RemoteEnv' 2>/dev/null || echo 'MISSING: $RemoteEnv'"

ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "${User}@${Host_}" $remote

[CmdletBinding(SupportsShouldProcess = $true)]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
# Fixed allowlist: original laws, published snapshots and the active .venv are excluded.
$Targets = @('tmp', '.venv-verify', '.pytest_cache', '.ruff_cache',
    'src\insurance_audit\__pycache__', 'src\insurance_audit\corpus\__pycache__',
    'scripts\__pycache__', 'tests\unit\__pycache__', 'tests\integration\__pycache__')
foreach ($RelativePath in $Targets) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $TargetPath)) { continue }
    $ResolvedTarget = (Resolve-Path -LiteralPath $TargetPath).Path
    if (-not $ResolvedTarget.StartsWith($ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Cleanup path is outside the project.'
    }
    if ((Get-Item -LiteralPath $ResolvedTarget -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Refusing a reparse-point cleanup target.'
    }
    if ($PSCmdlet.ShouldProcess($ResolvedTarget, 'Remove generated cache or redundant environment')) {
        Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
    }
}

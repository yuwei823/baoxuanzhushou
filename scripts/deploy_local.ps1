[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

function Write-Step([string]$text) { Write-Host "==> $text" -ForegroundColor Cyan }

# 1. 定位 Python：优先项目 .venv，缺失时用 py 启动器创建
$Py = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Py)) {
    Write-Step '首次部署：创建 .venv 并安装锁定依赖（约 1-2 分钟，需要网络）'
    function Test-Python([string]$command) {
        $parts = $command -split ' '
        $exe = $parts[0]
        $rest = @($parts | Select-Object -Skip 1) + @('-c', 'import sys')
        & $exe @rest 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    $Creator = $null
    foreach ($candidate in @('py -3.11', 'py -3', 'python')) {
        if (Test-Python $candidate) { $Creator = $candidate; break }
    }
    if (-not $Creator) {
        Write-Host '未找到 Python 3.11。请先安装 Python 3.11 或让 py 启动器可用，然后重新双击。' -ForegroundColor Red
        exit 1
    }
    $parts = $Creator -split ' '
    & $parts[0] @($parts | Select-Object -Skip 1) -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host '创建虚拟环境失败。' -ForegroundColor Red; exit 1 }
    & $Py -m pip install --disable-pip-version-check --require-hashes --no-deps -r requirements-build.lock
    if ($LASTEXITCODE -ne 0) { Write-Host '依赖安装失败（requirements-build.lock）。' -ForegroundColor Red; exit 1 }
    & $Py -m pip install --disable-pip-version-check --require-hashes --no-build-isolation -r requirements-dev.lock
    if ($LASTEXITCODE -ne 0) { Write-Host '依赖安装失败（requirements-dev.lock）。' -ForegroundColor Red; exit 1 }
    & $Py -m pip install --disable-pip-version-check --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { Write-Host '项目安装失败。' -ForegroundColor Red; exit 1 }
    Write-Host '依赖安装完成。'
}

# 2. 配置检查：.env 与密钥（不输出密钥内容）
$EnvFile = Join-Path $ProjectRoot '.env'
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item (Join-Path $ProjectRoot '.env.example') $EnvFile
    Write-Host '已生成 .env 模板，请先填写 DASHSCOPE_API_KEY 与 BAILIAN_BASE_URL，再重新双击。' -ForegroundColor Yellow
    exit 1
}
$EnvText = Get-Content -Raw -Encoding UTF8 $EnvFile
if ($EnvText -notmatch '(?m)^\s*DASHSCOPE_API_KEY\s*=\s*\S') {
    Write-Host 'DASHSCOPE_API_KEY 为空：服务将无法调用真实模型。请编辑 .env 后重新双击。' -ForegroundColor Yellow
    exit 1
}

# 3. hybrid 索引：缺失时询问是否构建（产生少量 Embedding 用量），否则本次以 BM25 启动
$Hybrid = $EnvText -notmatch '(?m)^\s*RETRIEVAL_MODE\s*=\s*bm25'
$IndexDir = Join-Path $ProjectRoot 'data\indexes'
if ($Hybrid -and -not (Get-ChildItem $IndexDir -File -ErrorAction SilentlyContinue)) {
    Write-Host 'hybrid 模式需要向量索引，当前缺失。' -ForegroundColor Yellow
    $Answer = Read-Host '现在构建索引（真实 Embedding 调用，约 18 次请求）？[Y/N]'
    if ($Answer -in @('Y', 'y')) {
        & $Py -m insurance_audit.cli build-index
        if ($LASTEXITCODE -ne 0) { Write-Host '索引构建失败，请检查 .env 与网络后重试。' -ForegroundColor Red; exit 1 }
    } else {
        $env:RETRIEVAL_MODE = 'bm25'
        Write-Host '本次以 BM25 模式启动；之后可运行 build-index 并重新部署恢复 hybrid。'
    }
}

# 4. 停止占用 8000 端口的旧服务
$Listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $Listeners) {
    Write-Host "停止旧服务进程 PID $($listener.OwningProcess) ..."
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# 5. 启动服务（独立窗口显示日志，关闭窗口即停止服务）
Write-Step '启动服务 http://127.0.0.1:8000'
$ServerArgs = @('-m', 'uvicorn', 'insurance_audit.api:app', '--host', '127.0.0.1', '--port', '8000')
Start-Process -FilePath $Py -ArgumentList $ServerArgs -WorkingDirectory $ProjectRoot

# 6. 等待就绪并打开浏览器
$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/readyz' -TimeoutSec 5
        if ($status.ready) { $Ready = $true; break }
    } catch { }
}
if ($Ready) {
    Write-Host '服务已就绪（' -NoNewline
    Write-Host $status.retrieval_mode -NoNewline -ForegroundColor Green
    Write-Host ' 模式）。'
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8000' }
} else {
    Write-Host '服务未在 60 秒内就绪，请查看新打开的 uvicorn 窗口中的日志。' -ForegroundColor Yellow
}
Write-Host '停止服务：双击 stop-local.bat，或直接关闭 uvicorn 窗口。'

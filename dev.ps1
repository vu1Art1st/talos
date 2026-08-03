<#
Talos 一键本地开发脚本（Windows）
- 后端：SQLite + 免队列模式，无需 Postgres/Redis，绑定 0.0.0.0:$BackendPort
- 前端：Vite Dev Server，绑定 0.0.0.0:$FrontendPort，支持通过 VPS_IP:PORT 外部访问
用法：powershell -ExecutionPolicy Bypass -File .\dev.ps1
可选：powershell -ExecutionPolicy Bypass -File .\dev.ps1 -FrontendPort 27014 -BackendPort 27015
#>
param(
    # 默认端口：前端 27014，后端 27015
    [int]$FrontendPort = 27014,
    [int]$BackendPort = 27015
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($cmd in 'python', 'node', 'npm') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "[dev] 未找到 $cmd，请先安装后重试" -ForegroundColor Red
        exit 1
    }
}

$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '[dev] 初始化后端虚拟环境并安装依赖...' -ForegroundColor Cyan
    python -m venv (Join-Path $backend '.venv')
    & $venvPython -m pip install -r (Join-Path $backend 'requirements-dev.txt')
}

if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host '[dev] 安装前端依赖...' -ForegroundColor Cyan
    Push-Location $frontend
    npm install 
    Pop-Location
}

Write-Host "[dev] 启动后端 http://0.0.0.0:$BackendPort （SQLite + 免队列）" -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    param($backend, $py, $port)
    Set-Location $backend
    $env:VP_DATABASE_URL = 'sqlite+aiosqlite:///./dev.db'
    $env:VP_DISABLE_QUEUE = '1'
    # 开发模式：开启 DEBUG（放宽密钥校验、暴露 API 文档），固定内置 admin 初始口令
    $env:VP_DEBUG = '1'
    $env:VP_INITIAL_ADMIN_PASSWORD = 'admin123'
    # --host 0.0.0.0：绑定所有网卡，否则仅 127.0.0.1 可访问（VPS 外部无法连接）
    & $py -m uvicorn app.main:app --reload --host 0.0.0.0 --port $port
} -ArgumentList $backend, $venvPython, $BackendPort

Write-Host ''
Write-Host "  前端(本机):  http://localhost:$FrontendPort" -ForegroundColor Green
Write-Host "  前端(外部):  http://<VPS_IP>:$FrontendPort （需放行 $FrontendPort 端口）" -ForegroundColor Green
Write-Host "  API 文档:    http://localhost:$BackendPort/api/docs" -ForegroundColor Green
Write-Host '  默认账号:    admin / admin123' -ForegroundColor Green
Write-Host '  Ctrl+C 退出（自动停止后端）' -ForegroundColor Yellow
Write-Host ''

try {
    Push-Location $frontend
    # 传递端口给 vite.config.ts（前端页面通过 Vite 代理访问后端，外部只需放行前端端口）
    $env:VP_FRONTEND_PORT = "$FrontendPort"
    $env:VP_BACKEND_PORT = "$BackendPort"
    npm run dev
} finally {
    Pop-Location
    Write-Host '[dev] 停止后端...' -ForegroundColor Cyan
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
}

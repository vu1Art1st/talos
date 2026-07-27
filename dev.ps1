<#
Talos 一键本地开发脚本（Windows）
- 后端：SQLite + 免队列模式，无需 Postgres/Redis，http://localhost:8000
- 前端：Vite Dev Server，http://localhost:5173
用法：powershell -ExecutionPolicy Bypass -File .\dev.ps1
#>
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

Write-Host '[dev] 启动后端 http://localhost:8000 （SQLite + 免队列）' -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    param($backend, $py)
    Set-Location $backend
    $env:VP_DATABASE_URL = 'sqlite+aiosqlite:///./dev.db'
    $env:VP_DISABLE_QUEUE = '1'
    & $py -m uvicorn app.main:app --reload --port 8000
} -ArgumentList $backend, $venvPython

Write-Host ''
Write-Host '  前端:     http://localhost:5173' -ForegroundColor Green
Write-Host '  API 文档: http://localhost:8000/api/docs' -ForegroundColor Green
Write-Host '  默认账号: admin / admin123' -ForegroundColor Green
Write-Host '  Ctrl+C 退出（自动停止后端）' -ForegroundColor Yellow
Write-Host ''

try {
    Push-Location $frontend
    npm run dev
} finally {
    Pop-Location
    Write-Host '[dev] 停止后端...' -ForegroundColor Cyan
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
}

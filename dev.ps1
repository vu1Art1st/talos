<#
Talos 一键本地开发脚本（Windows）
- 后端：SQLite + 免队列模式，无需 Postgres/Redis，绑定 0.0.0.0:$BackendPort
- 前端：Vite Dev Server，绑定 0.0.0.0:$FrontendPort，支持通过 VPS_IP:PORT 外部访问
- 内置端口冲突检测与健康检查：启动前检测端口占用；启动后轮询 HTTP 确认服务真正响应，
  发现端口冲突或「假启动」（进程存在但服务未监听）时明确提示并给出处理建议
用法：powershell -ExecutionPolicy Bypass -File .\dev.ps1
可选：powershell -ExecutionPolicy Bypass -File .\dev.ps1 -FrontendPort 27014 -BackendPort 27015 -HealthTimeout 30
环境变量（与 dev.sh 对齐）：VP_FRONTEND_PORT / VP_BACKEND_PORT / VP_HEALTH_TIMEOUT
#>
param(
    # 端口与健康检查超时：优先级为「显式参数 > 环境变量 > 默认值」
    [int]$FrontendPort,
    [int]$BackendPort,
    # 健康检查：等待服务可响应（HTTP）的最长秒数
    [int]$HealthTimeout
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 与 dev.sh 行为一致：允许同名环境变量覆盖默认端口与健康检查超时。
# 注意：必须先判断参数是否被显式传入（$PSBoundParameters），
# 否则脚本末尾写入的环境变量（VP_*_PORT）会残留到当前会话并覆盖下次的显式参数。
if (-not $PSBoundParameters.ContainsKey('FrontendPort')) {
    $FrontendPort = if ($env:VP_FRONTEND_PORT) { [int]$env:VP_FRONTEND_PORT } else { 27014 }
}
if (-not $PSBoundParameters.ContainsKey('BackendPort')) {
    $BackendPort = if ($env:VP_BACKEND_PORT) { [int]$env:VP_BACKEND_PORT } else { 27015 }
}
if (-not $PSBoundParameters.ContainsKey('HealthTimeout')) {
    $HealthTimeout = if ($env:VP_HEALTH_TIMEOUT) { [int]$env:VP_HEALTH_TIMEOUT } else { 30 }
}

$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

foreach ($cmd in 'python', 'node', 'pnpm') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "[dev] 未找到 $cmd，请先安装后重试" -ForegroundColor Red
        exit 1
    }
}

# ---------- 端口检测工具 ----------

# 端口是否处于 LISTEN 状态（Get-NetTCPConnection 优先，旧系统回退 netstat）
function Test-PortInUse {
    param([int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    }
    $line = netstat -ano | Select-String ":$Port\s+.*LISTENING" | Select-Object -First 1
    return [bool]$line
}

# 获取监听指定端口的进程 PID（尽力而为，无权限/无工具时返回 $null）
function Get-PortPid {
    param([int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($conn) { return [int]$conn.OwningProcess }
        return $null
    }
    $line = netstat -ano | Select-String ":$Port\s+.*LISTENING" | Select-Object -First 1
    if ($line) {
        $parts = ($line.ToString().Trim() -split '\s+')
        return [int]$parts[$parts.Count - 1]
    }
    return $null
}

# 按 PID 取进程名
function Get-ProcName {
    param([int]$ProcId)
    if (-not $ProcId) { return '' }
    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($p) { return $p.ProcessName }
    return '已退出'
}

# HTTP 探测：任何响应（含 401/404）都视为服务已监听
function Test-HttpOk {
    param([int]$Port, [string]$Path)
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port$Path" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        # PowerShell 对非 2xx 抛异常，但只要收到了 HTTP 响应即视为服务已监听
        if ($_.Exception.Response -ne $null) { return $true }
        return $false
    }
}

# 轮询等待服务就绪
function Wait-ServiceReady {
    param([int]$Port, [string]$Name, [string]$Path)
    for ($i = 0; $i -lt $HealthTimeout; $i++) {
        if (Test-HttpOk -Port $Port -Path $Path) {
            Write-Host "[dev] $Name 已就绪 http://127.0.0.1:$Port$Path" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

# 终止进程树（uvicorn --reload 会有 reloader + worker 父子进程）
function Stop-ProcessTree {
    param([int]$ProcId)
    if ($ProcId) { taskkill /PID $ProcId /T /F 2>$null | Out-Null }
}

# ---------- 提示信息 ----------

# 端口冲突提示 + 处理建议
function Write-ConflictAdvice {
    param([int]$Port, [string]$Name, [int]$ProcId, [string]$Pname)
    Write-Host ""
    Write-Host "[dev] ⚠ 端口 $Port 已被占用，$Name 无法启动！" -ForegroundColor Yellow
    if ($ProcId) {
        Write-Host "[dev] 占用进程: PID $ProcId（$Pname）"
    } else {
        Write-Host "[dev] 占用进程: 无法识别（权限不足或工具缺失）"
    }
    Write-Host "[dev] 该端口被占用时进程可能「假启动」（进程存在但服务监听失败）。"
    Write-Host "[dev] 处理建议（任选其一）："
    Write-Host "[dev]   1) 终止占用进程："
    if ($ProcId) {
        Write-Host "[dev]        Windows:      taskkill /PID $ProcId /F"
        Write-Host "[dev]        Linux/macOS:  kill -9 $ProcId"
    }
    Write-Host "[dev]   2) 更换端口启动："
    Write-Host "[dev]        Windows:      .\dev.ps1 -FrontendPort 27016 -BackendPort 27017"
    Write-Host "[dev]        Linux/macOS:  FRONTEND_PORT=27016 BACKEND_PORT=27017 bash dev.sh"
    Write-Host "[dev] 处理完成后重新运行本脚本。"
}

# 假启动（进程在但服务未响应）提示 + 处理建议
function Write-FakeStartAdvice {
    param([int]$Port, [string]$Name, [string]$Path)
    Write-Host ""
    Write-Host "[dev] ⚠ $Name 启动超时（${HealthTimeout} 秒内未响应 http://127.0.0.1:$Port$Path）" -ForegroundColor Yellow
    Write-Host "[dev] 进程可能仍在但服务未正常监听（假启动）。"
    Write-Host "[dev] 请查看上方 $Name 启动日志中的错误（Traceback / 报错信息）。"
    Write-Host "[dev] 常见原因：端口被占用、数据库被锁、依赖缺失、磁盘空间不足。"
    Write-Host "[dev] 可终止相关进程后重新运行本脚本。"
}

# ---------- 端口预检 ----------
Write-Host "[dev] 预检端口占用（端口冲突检测）..." -ForegroundColor Cyan
foreach ($check in @(@{ Port = $BackendPort; Name = '后端' }, @{ Port = $FrontendPort; Name = '前端' })) {
    if (Test-PortInUse -Port $check.Port) {
        $procId = Get-PortPid -Port $check.Port
        Write-ConflictAdvice -Port $check.Port -Name $check.Name -ProcId $procId -Pname (Get-ProcName -ProcId $procId)
        exit 1
    }
}
Write-Host "[dev] 端口检查通过：$BackendPort / $FrontendPort 均空闲。" -ForegroundColor Green

if (-not (Test-Path $venvPython)) {
    Write-Host '[dev] 初始化后端虚拟环境并安装依赖...' -ForegroundColor Cyan
    python -m venv (Join-Path $backend '.venv')
    & $venvPython -m pip install -r (Join-Path $backend 'requirements-dev.txt')
}

if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host '[dev] 安装前端依赖...' -ForegroundColor Cyan
    Push-Location $frontend
    pnpm install
    Pop-Location
}

$backendProc = $null
$frontendProc = $null

try {
    # 开发模式环境变量：SQLite + 免队列 + DEBUG（放宽密钥校验、暴露 API 文档）+ 固定内置 admin 初始口令
    # Start-Process 会继承当前会话环境变量，须在启动前后端前统一设置
    $env:VP_DATABASE_URL = 'sqlite+aiosqlite:///./dev.db'
    $env:VP_DISABLE_QUEUE = '1'
    $env:VP_DEBUG = '1'
    $env:VP_INITIAL_ADMIN_PASSWORD = 'admin123'

    # ---------- 启动后端（后台）并等待就绪 ----------
    Write-Host "[dev] 启动后端 http://0.0.0.0:$BackendPort （SQLite + 免队列）" -ForegroundColor Cyan
    $backendProc = Start-Process -FilePath $venvPython `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', "$BackendPort" `
        -WorkingDirectory $backend -NoNewWindow -PassThru

    if (-not (Wait-ServiceReady -Port $BackendPort -Name '后端' -Path '/api/v1/meta')) {
        Write-FakeStartAdvice -Port $BackendPort -Name '后端' -Path '/api/v1/meta'
        exit 1
    }

    # ---------- 启动前端（后台）并等待就绪 ----------
    Write-Host "[dev] 启动前端 http://0.0.0.0:$FrontendPort （Vite Dev Server）" -ForegroundColor Cyan
    # 传递端口给 vite.config.ts（前端页面通过 Vite 代理访问后端，外部只需放行前端端口）
    $env:VP_FRONTEND_PORT = "$FrontendPort"
    $env:VP_BACKEND_PORT = "$BackendPort"
    # Windows 上 pnpm 是 .cmd/.ps1 shim（mise/nvm 环境下尤其如此），Start-Process 无法直接执行，
    # 须经 cmd.exe /c 包装，与开发机上直接敲 pnpm 命令的行为一致
    $cmdExe = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $frontendProc = Start-Process -FilePath $cmdExe `
        -ArgumentList '/d', '/c', 'pnpm run dev' `
        -WorkingDirectory $frontend -NoNewWindow -PassThru

    if (-not (Wait-ServiceReady -Port $FrontendPort -Name '前端' -Path '/')) {
        Write-FakeStartAdvice -Port $FrontendPort -Name '前端' -Path '/'
        exit 1
    }

    Write-Host ''
    Write-Host "  前端(本机):  http://localhost:$FrontendPort" -ForegroundColor Green
    Write-Host "  前端(外部):  http://<VPS_IP>:$FrontendPort （需放行 $FrontendPort 端口）" -ForegroundColor Green
    Write-Host "  API 文档:    http://localhost:$BackendPort/api/docs" -ForegroundColor Green
    Write-Host '  默认账号:    admin / admin123' -ForegroundColor Green
    Write-Host '  Ctrl+C 退出（自动停止前后端）' -ForegroundColor Yellow
    Write-Host ''

    # 前台等待前端退出；Ctrl+C 时由 finally 统一清理
    Wait-Process -Id $frontendProc.Id
} finally {
    Write-Host '[dev] 停止后端...' -ForegroundColor Cyan
    Stop-ProcessTree -ProcId $backendProc.Id
    Write-Host '[dev] 停止前端...' -ForegroundColor Cyan
    Stop-ProcessTree -ProcId $frontendProc.Id
}

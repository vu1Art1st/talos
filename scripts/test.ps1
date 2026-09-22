<#
Talos 后端测试入口（Windows；与 scripts/test.sh 行为对齐）。

为什么需要它：跑测试有一串「记错就得到误导性结果」的必带项，本脚本把它们固化——
  1) 受管终端（WorkBuddy / CodeBuddy 沙箱）的删除守卫会打断 pytest 清理 basetemp，
     缺 CODEBUDDY_SAFE_DELETE_ENABLED=0 时的症状是「单个文件全绿、全量几十个 ERROR」；
  2) --basetemp 必须落在仓库内（系统临时目录会被守卫视为越界删除目标），且每次运行唯一
     （共用固定目录时并发跑两份测试会互相删掉对方的临时文件）；
  3) 测试库 schema 由 conftest 按进程派生（VP_DB_SCHEMA），无需在此指定；残留可用 -Prune 清理。

用法（仓库根目录；Windows 侧一律 pwsh 7，见 .codebuddy/rules/pwsh7.md）：
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Workers 4
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -PytestArgs '-k','retest','-x'
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -NoDepsCheck
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Prune -Yes
#>
param(
    # 并行 worker 数（>0 时启用 pytest-xdist；--dist loadscope 保证同一模块不拆散）
    [int]$Workers = 0,
    # 跳过 5432/6379 预检（CI 由 services 容器保证）
    [switch]$NoDepsCheck,
    # 清理残留 test_* schema 与 basetemp 后退出
    [switch]$Prune,
    # -Prune 的确认开关
    [switch]$Yes,
    # 透传给 pytest 的其余参数
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$PytestArgs
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root 'backend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '[test] 未找到 backend\.venv，请先按 AGENTS.md「常用命令」用 uv 创建并安装依赖' -ForegroundColor Red
    exit 1
}

function Test-PortListening {
    param([int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    }
    $line = netstat -ano | Select-String ":$Port\s+.*LISTENING" | Select-Object -First 1
    return [bool]$line
}

# ---------- 清理模式 ----------
if ($Prune) {
    if (-not $Yes) {
        Write-Host '[test] -Prune 会删除残留的 test_* schema 与 basetemp；确认无并发测试在跑后加 -Yes 执行' -ForegroundColor Yellow
        exit 2
    }
    Push-Location $backend
    try {
        & $venvPython -m scripts.prune_test_schemas --yes
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Pop-Location }
    $tmpRoot = Join-Path $backend '_pytest_tmp'
    if (Test-Path $tmpRoot) {
        Remove-Item -Recurse -Force (Join-Path $tmpRoot '*') -ErrorAction SilentlyContinue
        Write-Host '[test] 已清理 basetemp 目录' -ForegroundColor Green
    }
    exit 0
}

# ---------- 依赖服务预检 ----------
if (-not $NoDepsCheck) {
    foreach ($svc in @(@{ Port = 5432; Name = 'PostgreSQL(DBngin)' }, @{ Port = 6379; Name = 'Redis(DBngin)' })) {
        if (-not (Test-PortListening -Port $svc.Port)) {
            Write-Host "[test] ⚠ $($svc.Name) 未监听 127.0.0.1:$($svc.Port) —— 测试库/限流依赖它，请先启动（见 docs/LOCAL_DEV_SETUP.md）" -ForegroundColor Yellow
            exit 1
        }
    }
    Write-Host '[test] 依赖服务就绪：PostgreSQL(5432) / Redis(6379)' -ForegroundColor Green
}

# ---------- 运行 ----------
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$baseTemp = Join-Path $backend "_pytest_tmp\run_$PID`_$stamp"
New-Item -ItemType Directory -Force -Path $baseTemp | Out-Null

$argList = @('-m', 'pytest', '-p', 'no:cacheprovider', "--basetemp=$baseTemp")
if ($Workers -gt 0) {
    # loadscope：同一测试模块（用例间存在累积状态依赖）不拆到不同 worker
    $argList += @('-n', "$Workers", '--dist', 'loadscope')
    Write-Host "[test] 并行执行：$Workers 个 worker（每个 worker 独占一个 PostgreSQL schema）" -ForegroundColor Cyan
}
if ($PytestArgs) { $argList += $PytestArgs }

# 受管终端的删除守卫会打断 pytest 清理 basetemp（症状：单文件全绿、全量几十个 ERROR）
$env:CODEBUDDY_SAFE_DELETE_ENABLED = '0'

Write-Host "[test] $venvPython $($argList -join ' ')" -ForegroundColor Cyan
Push-Location $backend
try {
    & $venvPython @argList
    $code = $LASTEXITCODE
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $baseTemp -ErrorAction SilentlyContinue
}
exit $code

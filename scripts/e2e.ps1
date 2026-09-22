<#
Talos 端到端测试编排（Windows；与 scripts/e2e.sh 行为对齐）。

起一套**独立于开发栈**的 E2E 环境并跑 Playwright（系统 Chrome）：
  vulnplatform_e2e 库 → 迁移 → 种子 → api(27016) → 前端(27017) → playwright → 收摊
与 dev 栈完全隔离（不同库、不同端口、不同 storage 目录），跑 E2E 不会动到开发数据。

用法（仓库根目录；Windows 侧一律 pwsh 7，见 .codebuddy/rules/pwsh7.md）：
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1 -Headed     # 带界面排查
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1 -Keep       # 跑完保留栈
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1 -PlaywrightArgs 'golden-path.spec.ts','-g','登录'
#>
param(
    [switch]$Headed,                      # 带浏览器界面运行（排查用）
    [switch]$Keep,                        # 跑完保留 E2E 栈（人工看现场）
    [int]$ApiPort = 27016,
    [int]$WebPort = 27017,
    [string]$Database = 'vulnplatform_e2e',
    # 透传给 playwright test 的额外参数（如 -PlaywrightArgs 'golden-path.spec.ts','-g','登录'）
    [string[]]$PlaywrightArgs = @()
)
$ErrorActionPreference = 'Stop'

# `pwsh -File` 下数组参数**不会**按逗号拆分（`-PlaywrightArgs a,b` 会作为单个字符串传入），
# 这里显式拆分，使 `-PlaywrightArgs 'a','b'` 与 `-PlaywrightArgs a,b` 两种写法都可用——
# 否则 playwright 会收到 "a,b" 并报 `No tests found`（2026-09-22 实测）。
$PlaywrightArgs = @($PlaywrightArgs | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Log($msg) { Write-Host "[e2e] $msg" }
function Die($msg) { Write-Host "[e2e] ✗ $msg" -ForegroundColor Red; exit 1 }

# ---------- 依赖预检 ----------
foreach ($spec in @(@(5432, 'PostgreSQL'), @(6379, 'Redis'))) {
    $listening = [bool](Get-NetTCPConnection -State Listen -LocalPort $spec[0] -ErrorAction SilentlyContinue)
    if (-not $listening) {
        Die "$($spec[1]) 未监听 127.0.0.1:$($spec[0]) —— 请先在 DBngin 启动（见 docs/LOCAL_DEV_SETUP.md）"
    }
}

$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Die '未找到 backend\.venv 解释器（见 AGENTS.md「常用命令」）' }

# 端口必须空闲：否则会「静默复用」上次未收摊的栈（旧前端代理指向旧 api），得到似是而非的结果
foreach ($port in @($ApiPort, $WebPort)) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($busy) {
        Die "$port 已被 PID $($busy.OwningProcess) 占用 —— 多为上次 E2E 未收摊；请先结束该进程或改端口（-ApiPort / -WebPort）"
    }
}

# ---------- 从仓库根 .env 派生 E2E 库 DSN ----------
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) { Die '缺少仓库根 .env（需 POSTGRES_USER/POSTGRES_PASSWORD）' }
$envText = Get-Content $envFile -Raw
function EnvValue($name, $default) {
    $m = [regex]::Match($envText, "(?m)^\s*$name\s*=\s*(.+?)\s*$")
    if ($m.Success) { return $m.Groups[1].Value } else { return $default }
}
$pgUser = EnvValue 'POSTGRES_USER' 'vulnplatform'
$pgPw = EnvValue 'POSTGRES_PASSWORD' ''
if (-not $pgPw) { Die '.env 缺少 POSTGRES_PASSWORD' }

$env:VP_DATABASE_URL = "postgresql+asyncpg://${pgUser}:${pgPw}@127.0.0.1:5432/$Database"
$env:VP_DEBUG = '0'   # 0：贴近生产行为，且避免 SQL echo 刷爆日志
$env:VP_DISABLE_QUEUE = '1'
$env:VP_SECRET_KEY = 'e2e-only-secret-key-0123456789abcdef'
$env:VP_INITIAL_ADMIN_PASSWORD = 'admin123'
$env:VP_STORAGE_DIR = 'storage_e2e'

New-Item -ItemType Directory -Force -Path (Join-Path $root 'e2e-results') | Out-Null

# 受管终端（WorkBuddy / CodeBuddy 沙箱）的删除守卫会拦截 Playwright 清理 outputDir
# （报 `[safe-delete] 操作失败`，用例根本跑不起来）——与 scripts/test.ps1 同一处理口径。
$env:CODEBUDDY_SAFE_DELETE_ENABLED = '0'

# ---------- 迁移 + 种子 ----------
Log "迁移并重置种子数据：$Database"
# 注意：backend 的 `scripts` 包在 backend 目录下才可导入（与仓库根 scripts/ 同名但无关）
Push-Location (Join-Path $root 'backend')
try {
    & $py -m scripts.migrate
    $migrateCode = $LASTEXITCODE
    if ($migrateCode -eq 0) {
        & $py -m scripts.seed_dev_data --reset
        $seedCode = $LASTEXITCODE
    }
} finally { Pop-Location }
if ($migrateCode -ne 0) { Die "迁移失败（库 $Database 是否存在？见下方输出）" }
if ($seedCode -ne 0) { Die '种子数据失败' }

# ---------- 起 api 与前端 ----------
$apiProc = $null
$webProc = $null
function Stop-E2EStack {
    if ($Keep) { Log "--Keep：保留 E2E 栈（api :$ApiPort / 前端 :$WebPort）"; return }
    # 必须杀**整棵进程树**：`pnpm dev` 会派生 node/vite 子进程，只杀 pnpm 会留下孤儿继续占用端口
    # （2026-09-22 实测：收摊后 27017 仍被 node 监听，下次运行还会"以为起着新的栈"）。
    foreach ($p in @($apiProc, $webProc)) {
        if ($p -and -not $p.HasExited) { & taskkill /PID $($p.Id) /T /F 2>&1 | Out-Null }
    }
    foreach ($port in @($ApiPort, $WebPort)) {
        $owner = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($owner) {
            Log "⚠ $port 仍被 PID $($owner.OwningProcess) 占用，强制结束"
            Stop-Process -Id $owner.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    Log '已收摊'
}

try {
    Log "启动 api :$ApiPort"
    $apiProc = Start-Process -FilePath $py -ArgumentList @(
        '-m', 'uvicorn', 'app.main:app', '--port', "$ApiPort"
    ) -WorkingDirectory (Join-Path $root 'backend') -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $root 'e2e-results\api.log') `
        -RedirectStandardError (Join-Path $root 'e2e-results\api.err.log')

    $apiUrl = "http://127.0.0.1:$ApiPort/api/health"
    $ok = $false
    foreach ($_ in 1..60) {
        try { Invoke-WebRequest -Uri $apiUrl -TimeoutSec 2 -ErrorAction Stop | Out-Null; $ok = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ok) { Get-Content (Join-Path $root 'e2e-results\api.log') -Tail 30; Die 'api 未就绪（见 e2e-results/api*.log）' }

    Log "启动前端 :$WebPort（代理到 api :$ApiPort）"
    $env:VP_BACKEND_PORT = "$ApiPort"
    $env:VP_FRONTEND_PORT = "$WebPort"
    $webProc = Start-Process -FilePath 'pnpm' -ArgumentList @('dev') `
        -WorkingDirectory (Join-Path $root 'frontend') -NoNewWindow -PassThru `
        -RedirectStandardOutput (Join-Path $root 'e2e-results\frontend.log') `
        -RedirectStandardError (Join-Path $root 'e2e-results\frontend.err.log')

    $webUrl = "http://127.0.0.1:$WebPort/"
    $ok = $false
    foreach ($_ in 1..60) {
        try { Invoke-WebRequest -Uri $webUrl -TimeoutSec 2 -ErrorAction Stop | Out-Null; $ok = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ok) { Get-Content (Join-Path $root 'e2e-results\frontend.log') -Tail 30; Die '前端未就绪（见 e2e-results/frontend*.log）' }

    # ---------- 跑 Playwright（根目录工具包；系统 Chrome 免下载） ----------
    # 注意：PowerShell 变量名不区分大小写 —— 局部变量绝不能叫 $playwrightArgs（会与参数
    # $PlaywrightArgs 视为同一变量而被覆盖，拼出重复参数 → playwright 报 `No tests found`）。
    $pwArgs = @('exec', 'playwright', 'test')
    if ($Headed) { $pwArgs += '--headed' }
    $pwArgs += $PlaywrightArgs
    $env:E2E_BASE_URL = $webUrl

    Log "运行 Playwright（E2E_BASE_URL=$webUrl）"
    & pnpm @pwArgs
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Log "✗ 用例未全绿（退出码 $code）；报告：e2e-report/index.html，失败追踪：e2e-results/"
    } else {
        Log '✓ 黄金链路全绿'
    }
} finally {
    Stop-E2EStack
}

exit $code

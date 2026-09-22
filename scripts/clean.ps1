<#
Talos 本地垃圾文件清理（Windows；与 scripts/clean.sh 行为对齐）。

定位：**只清可再生的本地产物**（缓存 / 临时 / 构建输出 / 测试残留），
绝不碰数据类目录（备份、本机数据库、应用存储、venv、node_modules）。

为什么需要它：此前清理靠临时命令，容易「删一半、没删干净、或误删数据」——
实测 `Get-ChildItem -Recurse __pycache__ | Remove-Item` 会被静默跳过且无法核对。
本脚本把「哪些该删、哪些绝不能删、删了多少」固化成可复核的口径。

用法（仓库根目录；Windows 侧一律 pwsh 7）：
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean.ps1            # 预演（只列出，不删）
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean.ps1 -Apply     # 实际删除
  pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean.ps1 -Apply -IncludeVenv   # 连 .venv 内 __pycache__ 一起清
#>
param(
    # 实际删除；省略时为预演（只列出）
    [switch]$Apply,
    # 是否连 .venv / node_modules 内的缓存一起清（默认不清：清了对速度无益且有风险）
    [switch]$IncludeVenv
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# 绝不删除的路径（数据 / 依赖 / 配置）：任何目标命中即报错退出，避免脚本被改坏后误删
$protected = @(
    '.git', '.env', '.env.local', 'dev-database', 'backups', 'backend/storage',
    'backend/.venv', 'frontend/node_modules', '.codebuddy', '.qoder', '.workbuddy', 'design-demos'
)
$nodeModulesPattern = '\\node_modules\\'
$venvPattern = '\\\.venv\\'

function Assert-NotProtected {
    param([string]$FullPath)
    $rel = $FullPath.Substring($root.Length).TrimStart('\', '/') -replace '\\', '/'
    foreach ($p in $protected) {
        if ($rel -eq $p -or $rel.StartsWith("$p/")) {
            throw "[clean] 目标命中受保护路径，已中止：$rel（保护清单：$($protected -join ', ')）"
        }
    }
}

function Get-Targets {
    $items = @()

    # 1) Python 缓存（默认排除 .venv）
    $pycache = Get-ChildItem -Path $root -Recurse -Directory -Filter '__pycache__' -Force -ErrorAction SilentlyContinue
    foreach ($d in $pycache) {
        if (-not $IncludeVenv -and $d.FullName -match $venvPattern) { continue }
        if ($d.FullName -match $nodeModulesPattern) { continue }
        $items += $d
    }

    # 2) 工具缓存与测试临时目录
    foreach ($rel in '.pytest_cache', 'backend/.pytest_cache', 'backend/.ruff_cache', 'backend/_pytest_tmp') {
        $p = Join-Path $root $rel
        if (Test-Path $p) { $items += Get-Item $p -Force }
    }

    # 3) 前端构建产物（可再生）
    foreach ($rel in 'frontend/dist', 'frontend/dist_check') {
        $p = Join-Path $root $rel
        if (Test-Path $p) { $items += Get-Item $p -Force }
    }

    # 4) 测试存储残留（只清目录内容，目录本身保留）
    $testStorage = Join-Path $root 'backend/tests/test_storage'
    if (Test-Path $testStorage) {
        $items += Get-ChildItem $testStorage -Force -ErrorAction SilentlyContinue
    }

    # 5) 本地临时日志（仓库根与 backend：_*.txt / _*.log）
    foreach ($dir in @($root, (Join-Path $root 'backend'))) {
        $items += Get-ChildItem $dir -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^_.*\.(txt|log)$' }
    }

    return $items | Sort-Object -Property FullName -Unique
}

$targets = @(Get-Targets)
if ($targets.Count -eq 0) {
    Write-Host '[clean] 没有可清理的产物（仓库已干净）' -ForegroundColor Green
    exit 0
}

$total = 0
Write-Host ("[clean] 命中 {0} 项可清理产物：{1}" -f $targets.Count, $(if ($Apply) { '（-Apply 实际删除）' } else { '（预演，未删除；加 -Apply 执行）' })) -ForegroundColor Cyan
foreach ($t in $targets) {
    Assert-NotProtected -FullPath $t.FullName
    $size = if ($t.PSIsContainer) {
        (Get-ChildItem $t.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    } else { $t.Length }
    if (-not $size) { $size = 0 }
    $total += $size
    $rel = $t.FullName.Substring($root.Length).TrimStart('\', '/')
    Write-Host ("  {0,10} KB  {1}" -f [math]::Round($size / 1KB, 1), $rel)
}

Write-Host ("[clean] 合计可释放 {0} MB" -f [math]::Round($total / 1MB, 1)) -ForegroundColor Cyan

if ($Apply) {
    foreach ($t in $targets) {
        Assert-NotProtected -FullPath $t.FullName
        Remove-Item -Path $t.FullName -Recurse -Force -ErrorAction Continue
    }
    $left = @(Get-Targets).Count
    if ($left -gt 0) {
        Write-Host "[clean] ⚠ 仍有 $left 项未删除（可能被占用）。常见原因：正在运行的 python/uvicorn 占用 __pycache__。" -ForegroundColor Yellow
    } else {
        Write-Host '[clean] 已清理完毕' -ForegroundColor Green
    }
}

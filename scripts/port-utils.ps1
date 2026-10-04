# Windows 端口监听检测。
#
# 背景：部分主机上 Get-NetTCPConnection 会漏报 DBngin 等以其他权限运行的监听进程，
# 命令存在但返回空结果；此时必须回退 netstat，不能把“命令存在”当作“端口空闲”。
function Get-PortListeners {
    param([Parameter(Mandatory = $true)][int]$Port)

    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $listeners = @(
            Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
                Select-Object LocalAddress, LocalPort, OwningProcess
        )
        if ($listeners.Count -gt 0) { return $listeners }
    }

    $listeners = @()
    $lines = @(netstat -ano 2>$null | Select-String ":$Port\s+.*LISTENING\s+\d+\s*$")
    foreach ($line in $lines) {
        $parts = @($line.ToString().Trim() -split '\s+')
        if ($parts.Count -lt 5) { continue }
        $pidValue = 0
        if (-not [int]::TryParse($parts[$parts.Count - 1], [ref]$pidValue)) { continue }
        $listeners += [pscustomobject]@{
            LocalAddress = $parts[1]
            LocalPort = $Port
            OwningProcess = $pidValue
        }
    }
    return @($listeners)
}

function Test-PortInUse {
    param([int]$Port)
    return (@(Get-PortListeners -Port $Port).Count -gt 0)
}

function Test-PortListening {
    param([int]$Port)
    return (Test-PortInUse -Port $Port)
}

function Get-PortPid {
    param([int]$Port)
    $listener = @(Get-PortListeners -Port $Port) | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

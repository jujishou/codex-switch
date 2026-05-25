# 一键打包脚本（Windows / PowerShell）
# 跑法：pwsh ./build.ps1   或在 PowerShell 里  .\build.ps1
#
# 输出：dist_work/dist/codex-switch.exe
#       并复制到 release/codex-switch.exe

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root "src"
$work = Join-Path $root "dist_work"
$rel = Join-Path $root "release"

New-Item -ItemType Directory -Path $work -Force | Out-Null
New-Item -ItemType Directory -Path $rel -Force | Out-Null

Write-Host "[1/3] 装依赖（含 pyinstaller）..." -ForegroundColor Cyan
python -m pip install --quiet -r (Join-Path $root "requirements.txt") pyinstaller

Write-Host "[2/3] PyInstaller 打包..." -ForegroundColor Cyan
Push-Location $work
try {
    python -m PyInstaller `
        --onefile --windowed `
        --name "codex-switch" `
        --paths $src `
        --hidden-import tomlkit `
        --hidden-import adapter `
        --collect-data customtkinter `
        --clean --noconfirm `
        (Join-Path $src "gui_ctk.py")
} finally {
    Pop-Location
}

$builtExe = Join-Path $work "dist\codex-switch.exe"
$relExe = Join-Path $rel "codex-switch.exe"
Copy-Item $builtExe $relExe -Force

Write-Host "[3/3] 完成 ->  $relExe" -ForegroundColor Green
Get-Item $relExe | Select-Object Name, @{n='SizeMB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime

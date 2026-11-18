# 编译 MDReader 为 Windows 单文件可执行程序 (dist\MDReader.exe)
# 用法:  powershell -ExecutionPolicy Bypass -File build.ps1           (单文件 exe)
#        powershell -ExecutionPolicy Bypass -File build.ps1 -OneDir   (文件夹版, 启动更快)
param([switch]$OneDir)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> 检查依赖" -ForegroundColor Cyan
python -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }

Write-Host "==> 生成图标与示例图片" -ForegroundColor Cyan
python tools\make_assets.py
if ($LASTEXITCODE -ne 0) { throw "生成图标失败" }

Write-Host "==> PyInstaller 打包" -ForegroundColor Cyan
$mode = if ($OneDir) { "--onedir" } else { "--onefile" }
python -m PyInstaller --noconfirm --clean $mode --windowed `
    --name MDReader `
    --icon assets\app.ico `
    --version-file version_info.txt `
    --hidden-import PyQt6.QtSvg `
    --collect-submodules pygments.lexers `
    --collect-submodules pygments.styles `
    --exclude-module tkinter `
    --exclude-module unittest `
    --exclude-module pydoc `
    main.py
if ($LASTEXITCODE -ne 0) { throw "打包失败" }

$exe = if ($OneDir) { Join-Path $PSScriptRoot "dist\MDReader\MDReader.exe" } else { Join-Path $PSScriptRoot "dist\MDReader.exe" }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "==> 完成: $exe ($size MB)" -ForegroundColor Green

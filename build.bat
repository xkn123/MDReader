@echo off
rem 双击即可编译, 生成 dist\MDReader.exe
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
pause

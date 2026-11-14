@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Environnement Python absent. Executez d'abord Install-Idleon-Darts.ps1.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m idleon_darts gui --data-dir "..\local\idleon-darts-app"

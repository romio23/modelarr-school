@echo off
schtasks /Delete /TN "Modelarr" /F
schtasks /Delete /TN "3D Modelbibliotheek" /F >nul 2>&1
pause

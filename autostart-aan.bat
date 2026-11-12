@echo off
rem Start Modelarr automatisch (geminimaliseerd) zodra je inlogt op Windows.
schtasks /Delete /TN "3D Modelbibliotheek" /F >nul 2>&1
schtasks /Create /TN "Modelarr" /TR "cmd /c start /min \"\" \"%~dp0start-windows.bat\" silent" /SC ONLOGON /F
if errorlevel 1 (
  echo Mislukt. Probeer dit bestand als Administrator te starten.
) else (
  echo Klaar: de app start voortaan bij inloggen. Uitzetten: autostart-uit.bat
)
pause

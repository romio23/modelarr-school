@echo off
setlocal
cd /d "%~dp0"
rem ===================== Instellingen (pas aan) =====================
rem Map(pen) met 3D-modellen, komma-gescheiden. Gebruik voor netwerkshares liever UNC-paden (\\nas\modellen)
rem dan een stationsletter (X:), want die is niet altijd beschikbaar bij automatisch starten.
set "MODELS_DIR="
set "PORT=8765"
rem 127.0.0.1 = alleen op deze pc. Zet op 0.0.0.0 om de app ook vanaf andere apparaten te openen
rem (maak dan eerst een account aan via Instellingen - Gebruikers of met AUTH_USER / AUTH_PASS).
set "HOST=127.0.0.1"
rem Standaard alleen indexeren. Zet de volgende regel aan om hernoemen/verplaatsen toe te staan (ook per root folder in de app in te stellen).
rem set "ALLOW_ORGANIZE=1"
rem Waar de dagelijkse back-ups komen (standaard: de map "backups" in config). Ook in de app in te stellen.
rem set "BACKUP_DIR=D:\Back-ups\Modelarr"
rem set "AUTH_USER=admin"
rem set "AUTH_PASS=kies-een-wachtwoord"
rem Database, thumbnails en logs staan standaard in de map "config" naast dit bestand (CONFIG_DIR om te wijzigen).
rem ==================================================================
set "OPEN_BROWSER=1"
if /i "%~1"=="silent" set "OPEN_BROWSER=0"
set "PYTHONUTF8=1"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (where python >nul 2>&1 && set "PY=python")
if not defined PY (
  echo Python 3.10 of nieuwer is nodig: https://www.python.org/downloads/
  echo Vink bij de installatie "Add python.exe to PATH" aan en start dit bestand daarna opnieuw.
  pause
  exit /b 1
)
if not exist venv\Scripts\python.exe (
  echo Eerste keer: virtuele omgeving maken en onderdelen installeren, dit duurt even...
  %PY% -m venv venv
  if errorlevel 1 (pause & exit /b 1)
)
venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo Modelarr start op http://127.0.0.1:%PORT%  (sluit dit venster om te stoppen)
venv\Scripts\python.exe app.py
pause

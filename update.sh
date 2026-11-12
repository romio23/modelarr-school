#!/bin/sh
# Modelarr bijwerken zonder je instellingen te verliezen.
#
# Gebruik (in de map waar je docker-compose.yml staat):
#   sh update.sh                      -> pakt de nieuwste modelarr.zip uit deze map of uit Downloads
#   sh update.sh pad/naar/nieuw.zip   -> gebruikt dat zipbestand
#   sh update.sh pad/naar/uitgepakte-map
#   sh update.sh --upgrade            -> ook de onderdelen (Python-pakketten, en bij Docker de basis-image) vernieuwen
#
# Werkt voor Docker (map met docker-compose.yml) én voor de LXC (map /opt/modelarr met venv).
# Wordt NIET overschreven: config/ (database, thumbnails, instellingen), docker-compose.yml en .env
set -e
cd "$(dirname "$0")"
SRC=""; UPGRADE=0
for a in "$@"; do case "$a" in --upgrade|-u) UPGRADE=1 ;; *) SRC="$a" ;; esac; done
if [ -z "$SRC" ]; then
  for d in . "$HOME/Downloads" /volume1/homes/*/Downloads; do
    f=$(ls -t "$d"/modelarr*.zip "$d"/modelbibliotheek-docker*.zip 2>/dev/null | head -n 1 || true)
    [ -n "$f" ] && { SRC="$f"; break; }
  done
fi
[ -n "$SRC" ] || { echo "Geen zipbestand gevonden. Gebruik: sh update.sh pad/naar/modelarr.zip"; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ -d "$SRC" ]; then
  cp -R "$SRC"/. "$TMP"/
else
  echo "Uitpakken: $SRC"
  if command -v unzip >/dev/null 2>&1; then unzip -q "$SRC" -d "$TMP"
  elif command -v 7z >/dev/null 2>&1; then 7z x -y -o"$TMP" "$SRC" >/dev/null
  elif command -v python3 >/dev/null 2>&1; then python3 -m zipfile -e "$SRC" "$TMP"
  else echo "Geen unzip, 7z of python3 gevonden: pak de zip zelf uit en geef de map op."; exit 1; fi
fi
NEW="$TMP"; [ -f "$NEW/app.py" ] || NEW=$(dirname "$(find "$TMP" -name app.py | head -n 1)")
[ -f "$NEW/app.py" ] || { echo "Dit lijkt geen Modelarr-zip (app.py ontbreekt)."; exit 1; }
OLD=$(grep -o "VERSION *= *'[^']*'" app.py 2>/dev/null | head -n 1 || true)
echo "Huidige versie: ${OLD:-onbekend}"
# alles kopiëren behalve je eigen instellingen
for item in "$NEW"/* "$NEW"/.dockerignore; do
  [ -e "$item" ] || continue
  n=$(basename "$item")
  case "$n" in config|docker-compose.yml|.env|tests|__pycache__|venv) continue ;; esac
  if [ "$n" = update.sh ]; then cp "$item" ./update.sh.new && mv ./update.sh.new ./update.sh; continue; fi  # niet midden in het draaien overschrijven
  rm -rf "./$n"
  cp -R "$item" "./$n"
done
echo "Nieuwe versie: $(grep -o "VERSION *= *'[^']*'" app.py | head -n 1)"
if [ -x ./venv/bin/pip ]; then  # LXC / systemd
  echo "Python-pakketten bijwerken…"
  if [ "$UPGRADE" = 1 ]; then ./venv/bin/pip install --disable-pip-version-check -q -U -r requirements.txt; else ./venv/bin/pip install --disable-pip-version-check -q -r requirements.txt; fi
  systemctl restart modelarr
  echo "Klaar: de service is opnieuw gestart. Open Modelarr opnieuw in je browser (Ctrl+F5)."
  [ "$UPGRADE" = 1 ] && echo "Tip: werk ook het systeem zelf bij met: apt-get update && apt-get -y upgrade"
  exit 0
fi
if docker compose version >/dev/null 2>&1; then DC="docker compose"; elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; else
  echo "Bestanden zijn bijgewerkt. Docker niet gevonden: bouw de container opnieuw (Container Manager → Project → Opnieuw opbouwen)."; exit 0; fi
if [ "$UPGRADE" = 1 ]; then $DC build --pull --no-cache; fi  # nieuwste basis-image en pakketten (anders hergebruikt Docker de oude laag)
$DC up -d --build --remove-orphans
echo "Klaar. Open Modelarr opnieuw in je browser (Ctrl+F5)."

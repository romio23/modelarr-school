#!/bin/sh
# Installatie in een Debian/Ubuntu LXC (als root, vanuit deze map):  sh install-lxc.sh
# Eerder geïnstalleerd onder de oude naam "modelbibliotheek"? Dit script neemt database, thumbnails en instellingen over.
set -e
apt-get update && apt-get install -y python3 python3-venv

# --- migratie van de oude naam (modelbibliotheek -> modelarr) ---
if [ -d /var/lib/modelbibliotheek ] && [ ! -e /var/lib/modelarr ]; then
  systemctl stop modelbibliotheek 2>/dev/null || true
  systemctl disable modelbibliotheek 2>/dev/null || true
  rm -f /etc/systemd/system/modelbibliotheek.service
  mv /var/lib/modelbibliotheek /var/lib/modelarr
  echo "Oude installatie overgenomen: /var/lib/modelbibliotheek -> /var/lib/modelarr"
fi
if [ -f /etc/modelbibliotheek.env ] && [ ! -f /etc/modelarr.env ]; then
  sed 's#/var/lib/modelbibliotheek#/var/lib/modelarr#' /etc/modelbibliotheek.env > /etc/modelarr.env
  rm -f /etc/modelbibliotheek.env
fi
[ -d /opt/modelbibliotheek ] && [ "$(pwd)" != /opt/modelbibliotheek ] && rm -rf /opt/modelbibliotheek

mkdir -p /opt/modelarr /var/lib/modelarr
cp -r . /opt/modelarr/
python3 -m venv /opt/modelarr/venv
/opt/modelarr/venv/bin/pip install -r /opt/modelarr/requirements.txt
[ -f /etc/modelarr.env ] || cat > /etc/modelarr.env <<'ENV'
CONFIG_DIR=/var/lib/modelarr
MODELS_DIR=/mnt/3d-modellen
PORT=8765
#BACKUP_DIR=/mnt/back-ups
#AUTH_USER=admin
#AUTH_PASS=kies-een-wachtwoord
#THUMB_WORKERS=2
ENV
cat > /etc/systemd/system/modelarr.service <<'UNIT'
[Unit]
Description=Modelarr
After=network-online.target remote-fs.target

[Service]
EnvironmentFile=/etc/modelarr.env
WorkingDirectory=/opt/modelarr
ExecStart=/opt/modelarr/venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now modelarr
systemctl restart modelarr
echo "Klaar. Pas /etc/modelarr.env aan (MODELS_DIR) en draai: systemctl restart modelarr"
echo "Open http://$(hostname -I | cut -d' ' -f1):8765"

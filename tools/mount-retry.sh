#!/bin/sh
# Koppelt netwerkshares (cifs/nfs uit /etc/fstab) elke minuut opnieuw als ze er niet zijn.
# In een LXC-container werkt x-systemd.automount niet; als de NAS bij het opstarten nog uit staat of het
# netwerk nog niet klaar is, blijft de map anders leeg. Draai dit eenmalig als root: sh tools/mount-retry.sh
set -e
[ "$(id -u)" = 0 ] || { echo "Draai dit als root."; exit 1; }
cat > /etc/systemd/system/modelarr-mount-retry.service <<'UNIT'
[Unit]
Description=Koppel de netwerkshares als ze ontbreken
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'mount -a -t cifs,nfs,nfs4 || true'
UNIT
cat > /etc/systemd/system/modelarr-mount-retry.timer <<'UNIT'
[Unit]
Description=Probeer elke minuut de netwerkshares te koppelen

[Timer]
OnBootSec=20
OnUnitActiveSec=60

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now modelarr-mount-retry.timer
echo "Klaar: ontbrekende netwerkshares worden elke minuut opnieuw gekoppeld."

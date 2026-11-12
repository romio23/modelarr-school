# Modelarr (server-versie)

> Deze app is gemaakt met behulp van [Claude](https://claude.ai/) (Anthropic). Ja, via vibecode.

> English documentation: [README-EN.md](https://github.com/romio23/modelarr/blob/main/README-EN.md)

Modelarr beheert je 3D-modellen zoals Sonarr en Radarr je films en series beheren.

Beheer je 3D-modellen zoals Sonarr/Radarr je films beheert: root folders, live bestandswachter,
automatische thumbnails, categorieën, wachtrij/geschiedenis, taken, logs en statuspagina.

## Windows (zonder Docker of Proxmox)
1. Installeer Python 3.10+ van python.org (vink "Add python.exe to PATH" aan).
2. Open `start-windows.bat` met Kladblok en vul `MODELS_DIR` in (bijv. `D:\3D` of `\\nas\modellen`). Daarna dubbelklikken.
   De eerste keer worden de onderdelen geïnstalleerd; de browser opent vanzelf op http://127.0.0.1:8765.
3. Automatisch starten bij inloggen: `autostart-aan.bat` (uitzetten met `autostart-uit.bat`).

Netwerkshares: gebruik een UNC-pad (`\\nas\modellen`: server én share) in plaats van een stationsletter; een geplande taak ziet gekoppelde stationsletters niet altijd.
Je kunt zo'n pad typen of plakken, ook met de aanhalingstekens van "Kopiëren als pad" in Verkenner: in de mapkiezer, of direct in het veld onder Instellingen → Mediabeheer.
Staat een share al gekoppeld aan een stationsletter, dan toont de mapkiezer het bijbehorende netwerkpad en kun je dat met één klik kiezen.
Het Windows-account waaronder de app draait moet toegang tot de share hebben. Vraagt de share om inloggegevens, sla ze dan op in Windows: `cmdkey /add:nas /user:gebruiker /pass:wachtwoord`.
Wil je de app vanaf andere apparaten openen, zet dan `HOST=0.0.0.0` én een account (Instellingen → Gebruikers); Windows vraagt dan om firewall-toestemming.
Database, thumbnails en logs staan in de map `config` naast de app. Wil je de dagelijkse back-ups op een andere schijf, zet dan `BACKUP_DIR` in `start-windows.bat` of stel de map in bij Instellingen → Mediabeheer (zie "Back-ups"). Niet getest op Windows door de ontwikkelaar: meld problemen met het logbestand `config\modelarr.log`.

## Installatie op Docker of Proxmox

Windows staat hierboven. Voor de andere plekken zijn er stap-voor-stap handleidingen:

1. **Docker op een Synology** (Container Manager)
2. **Docker op een gewone Linux-server of pc**
3. **Proxmox LXC** (zonder Docker)

Wat voor alle drie geldt:

- Modelarr gebruikt poort **8765**, niet 5000 (die gebruikt Synology DSM).
- Paden in de app zijn altijd paden **zoals de app ze ziet**: `/models` in Docker, `/mnt/3d-modellen` in de LXC. Nooit het pad op je NAS.
- Houd de database (`config`) **lokaal** bij de app, niet op een netwerkshare. Je back-ups zet je juist wél het liefst op een andere plek (zie "Back-ups").
- Draai maar één exemplaar tegelijk op dezelfde database.

### Docker op een Synology (Container Manager)

Geschreven voor DSM 7.2 en Container Manager; niet op elke DSM-versie uitgeprobeerd. De namen van menu's kunnen per versie iets verschillen.

**Voorbereiding**

1. Installeer **Container Manager** via het Pakketcentrum.
2. Zorg voor drie mappen (Configuratiescherm → Gedeelde map):
   - je modelmap, bijvoorbeeld `3D` (pad `/volume1/3D`);
   - een map voor het programma, bijvoorbeeld de gedeelde map `docker` met daarin de map `modelarr` (pad `/volume1/docker/modelarr`);
   - een map voor de back-ups, bijvoorbeeld de gedeelde map `Backups` met daarin de map `modelarr` (pad `/volume1/Backups/modelarr`). Kies hiervoor bij voorkeur een ander volume of een externe schijf, zodat een back-up niet op dezelfde schijf staat als het origineel.
3. Zoek het gebruikers-ID op dat Modelarr gebruikt. Zet SSH aan (Configuratiescherm → Terminal & SNMP), log in en typ `id jouwgebruiker`. Noteer `uid` en `gid` (bijvoorbeeld `1026` en `100`).
4. Geef die gebruiker rechten (Configuratiescherm → Gedeelde map → de map → Bewerken → Machtigingen):
   - modelmap: **lezen**; alleen **lezen/schrijven** als je Modelarr bestanden wilt laten hernoemen of naar de prullenbak laten verplaatsen;
   - `docker`: **lezen/schrijven** (de database en thumbnails komen in `docker/modelarr/config`);
   - `Backups`: **lezen/schrijven**.

**Installeren**

5. Upload `modelarr.zip` met File Station naar `docker/modelarr` en kies rechtermuisknop → **Uitpakken**. Het bestand `docker-compose.yml` moet direct in `/volume1/docker/modelarr` staan. Staat het in een extra map `modelarr`, verplaats dan de inhoud één niveau omhoog.
6. Open `docker-compose.yml` en pas aan (haal de `#` weg waar dat staat):

   ```yaml
   user: "1026:100"                 # uid:gid uit stap 3
   environment:
     - TZ=Europe/Amsterdam
     - MODELS_DIR=/models
     - BACKUP_DIR=/backups          # hier komen de dagelijkse back-ups
     - THUMB_WORKERS=3              # DS423: 3 is veilig
   volumes:
     - ./config:/config
     - /volume1/3D:/models          # zet :ro erachter als de app niets mag wijzigen
     - /volume1/Backups/modelarr:/backups
   ```

7. Open Container Manager → **Project** → **Aanmaken**. Geef de naam `modelarr`, kies als pad `/volume1/docker/modelarr` en laat DSM het bestaande `docker-compose.yml` gebruiken. Bouwen en starten duurt een paar minuten. Via SSH kan het ook: `cd /volume1/docker/modelarr && sudo docker compose up -d --build`.
8. Open `http://<ip-van-de-nas>:8765`. Door `MODELS_DIR=/models` staat je modelmap er al als root folder in en begint de eerste scan. Bij tienduizenden modellen kost dat uren, vooral de thumbnails; zie "Sneller thumbnails maken (NAS)".
9. Maak een account aan (Instellingen → Gebruikers) als je Modelarr ook buiten je eigen apparaat gebruikt.

**Controleren**

- Instellingen → Mediabeheer → **Back-upmap** laat `/backups` zien. Klik op **Nu back-uppen** en kijk in File Station of er een `library-….db` in `Backups/modelarr` staat.
- Staat er een melding "Back-upmap is niet beschrijfbaar", geef dan de gebruiker uit stap 3 schrijfrechten op `Backups`.
- Zet je back-upmap ook in een Hyper Backup-taak naar een externe schijf of cloud, zodat je geen back-up hebt die alleen op de NAS zelf staat.

**Bijwerken:** zie "Bijwerken". Let op: `update.sh` overschrijft je eigen `docker-compose.yml` niet. Heb je Modelarr al draaien, voeg dan de regels `BACKUP_DIR` en het volume `/backups` zelf toe en bouw opnieuw.

### Docker op een gewone Linux-server of pc

Voor een Linux-server of een VM met Docker, bijvoorbeeld Ubuntu of Debian.

1. **Docker installeren.** Volg de handleiding voor je systeem op https://docs.docker.com/engine/install/ (op Windows of macOS: Docker Desktop). Controleer met `docker compose version`.
2. **Modelarr uitpakken:**
   ```
   unzip modelarr.zip && cd modelarr
   ```
3. **Je gebruikers-ID opzoeken:** `id -u` en `id -g`. Zet die in `docker-compose.yml` bij `user:` (bijvoorbeeld `"1000:1000"`), zodat de app je bestanden kan lezen.
4. **De modelmap beschikbaar maken.** Staan je modellen op de server zelf, gebruik dan dat pad. Staan ze op een NAS, mount de share dan eerst op de host. Voorbeeld voor SMB in `/etc/fstab`, met een inlogbestand dat je zo maakt:
   ```
   apt-get install -y cifs-utils
   mkdir -p /mnt/3d
   cat > /root/.smbcred <<'EOT'
   username=GEBRUIKER
   password=WACHTWOORD
   EOT
   chmod 600 /root/.smbcred
   echo '//192.168.1.10/3d /mnt/3d cifs credentials=/root/.smbcred,ro,uid=1000,gid=1000,vers=3.0,iocharset=utf8,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0' >> /etc/fstab
   systemctl daemon-reload && mount -a && ls /mnt/3d
   ```
   Haal `ro` weg als Modelarr bestanden mag hernoemen of naar de prullenbak verplaatsen. `uid=1000,gid=1000` moet overeenkomen met `user:` in je compose-bestand. Over `x-systemd.automount`: zie "Share na een herstart" hieronder. Werkt het niet? Zie de tabel met meldingen bij de LXC-handleiding hieronder: de oorzaken zijn dezelfde.
5. **Een back-upmap kiezen** en maken, het liefst op een andere schijf of een NAS-share:
   ```
   mkdir -p /mnt/back-ups/modelarr
   ```
6. **`docker-compose.yml` aanpassen** (haal de `#` weg waar dat staat):
   ```yaml
   environment:
     - MODELS_DIR=/models
     - BACKUP_DIR=/backups
   volumes:
     - ./config:/config
     - /mnt/3d:/models                    # :ro als de app niets mag wijzigen
     - /mnt/back-ups/modelarr:/backups
   ```
7. **Starten:**
   ```
   docker compose up -d --build
   docker compose logs -f        # meekijken; stoppen met Ctrl+C
   ```
   Open `http://<ip-van-de-server>:8765`.
8. **Controleren:** Instellingen → Mediabeheer → **Nu back-uppen**, en kijk of er een `library-….db` in `/mnt/back-ups/modelarr` staat.

**Docker Desktop op Windows of macOS:** gebruik daar paden zoals `D:/3D:/models` en haal de regel `user:` weg. Op Windows is `start-windows.bat` (zie boven) meestal eenvoudiger en sneller.

**Bijwerken:** zie "Bijwerken". `update.sh` overschrijft je eigen `docker-compose.yml` niet: voeg bij een bestaande installatie de back-upregels zelf toe.

### Proxmox LXC (zonder Docker): stap voor stap

Een LXC is een lichte container met een eigen Debian of Ubuntu. Deze handleiding is geschreven voor het sjabloon `debian-13-standard_13.6-1_amd64.tar.zst`; met Ubuntu zijn de stappen hetzelfde. Alle commando's draai je als `root` in de console van de container.

**1. Container maken** (Proxmox → rechtsboven **Create CT**)

| Tabblad | Instelling |
|---|---|
| General | Hostname `modelarr`, een root-wachtwoord. Zet **"Unprivileged container" uit**; dan kun je later de NAS-share mounten. |
| Template | `debian-13-standard_13.6-1_amd64.tar.zst` (of een Ubuntu-sjabloon) |
| Disks | 10 GB of meer. Database en thumbnails komen hier ook op (tienduizenden thumbnails nemen een paar GB). |
| CPU | 2 cores |
| Memory | **4096 MB**, swap 512 MB. Met 2048 MB zit het geheugen tijdens de eerste scan van tienduizenden modellen vol en gaat de container swappen (traag, veel schijfactiviteit). |
| Network | Bridge `vmbr0`, IPv4 via DHCP (geef hem in je router een vast adres) of een vast IP |
| Confirm | Vink "Start after created" aan |

Heb je de container al met minder geheugen gemaakt? Verhoog het achteraf: container → **Resources → Memory → Edit**. Dat werkt direct, je hoeft niets opnieuw te installeren.

**2. SMB/CIFS toestaan.** Ga naar de container → **Options → Features → Edit**, vink **SMB/CIFS** aan en herstart de container.

**3. Bijwerken en gereedschap installeren** (Console van de container, inloggen als `root`):

```
apt-get update && apt-get -y upgrade
apt-get install -y unzip cifs-utils
```

**4. De NAS-share koppelen.** Maak eerst een inlogbestand. Gebruik een editor zoals hieronder en niet `printf`: een wachtwoord met `%` of `\` gaat er anders fout in. Let op de gebruikersnaam: een typefout geeft "Permission denied".

```
mkdir -p /mnt/3d-modellen
cat > /root/.smbcred <<'EOT'
username=JOUWGEBRUIKER
password=JOUWWACHTWOORD
EOT
chmod 600 /root/.smbcred
echo '//192.168.1.10/3d /mnt/3d-modellen cifs credentials=/root/.smbcred,ro,vers=3.0,iocharset=utf8,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0' >> /etc/fstab
systemctl daemon-reload
mount -a
ls /mnt/3d-modellen
```

De laatste opdracht moet je mappen laten zien. `ro` betekent alleen lezen. `x-systemd.automount` zorgt dat de share pas gekoppeld wordt als iets de map opent, en dat het later opnieuw geprobeerd wordt als de NAS bij het opstarten nog uit stond (zie "Share na een herstart" hieronder). Wil je dat Modelarr bestanden mag hernoemen of naar de prullenbak verplaatsen, gebruik dan `rw` en geef het account schrijfrechten op de Synology.

Staat er al een regel voor deze share in `/etc/fstab` en wil je een optie wijzigen? Verwijder de oude regel (`nano /etc/fstab`), draai `umount /mnt/3d-modellen` en daarna `mount -a`. `mount -o remount` werkt niet voor CIFS-opties.

**5. Het zipbestand in de container krijgen.** Het makkelijkst gaat het via de share: zet `modelarr.zip` vanaf je pc in een nieuwe map `_install` op de share, en pak hem uit:

```
mkdir -p /root/inst && cd /root/inst
unzip /mnt/3d-modellen/_install/modelarr.zip
cd modelarr
```

Verwijder de map `_install` daarna weer van de share. Liever zonder share? Zet SSH aan in de container (`apt-get install -y openssh-server`, zet `PermitRootLogin yes` in `/etc/ssh/sshd_config` en draai `systemctl restart ssh`) en kopieer vanaf je pc met `scp modelarr.zip root@<ip>:/root/`. Zet root-inloggen met wachtwoord daarna weer uit.

**6. Installeren:**

```
sh install-lxc.sh
```

Het script installeert Python en de onderdelen, zet het programma in `/opt/modelarr`, bewaart je gegevens in `/var/lib/modelarr` en maakt een service die bij het opstarten mee start. Het duurt een paar minuten. De map `/mnt/3d-modellen` uit stap 4 is de standaard `MODELS_DIR`. Controleer met:

```
systemctl status modelarr
hostname -I
```

**7. Openen.** Ga naar `http://<ip-van-de-container>:8765`. De eerste scan start vanzelf. Volg de voortgang in de app, of in de console met `journalctl -u modelarr -f`.

**8. Een back-upmap instellen.** Kies een plek op een andere machine dan de container, bijvoorbeeld een tweede share op de NAS. Maak op de NAS een gedeelde map `Backups` (met schrijfrechten voor hetzelfde account) en koppel hem in de container:

```
mkdir -p /mnt/back-ups
echo '//192.168.1.10/Backups /mnt/back-ups cifs credentials=/root/.smbcred,rw,vers=3.0,iocharset=utf8,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0' >> /etc/fstab
systemctl daemon-reload
mount -a
mkdir -p /mnt/back-ups/modelarr
```

Zet daarna de map in `/etc/modelarr.env` (open met `nano /etc/modelarr.env`):

```
BACKUP_DIR=/mnt/back-ups/modelarr
```

Draai `systemctl restart modelarr`. Je kunt de map ook in de app instellen (Instellingen → Mediabeheer → **Back-upmap**); die instelling gaat voor. Klik op **Nu back-uppen** en kijk of er een `library-….db` in `Backups/modelarr` op de NAS staat.

Maak de map `/mnt/back-ups/modelarr` bewust zelf aan, **terwijl de share gekoppeld is**. Modelarr maakt een ontbrekende back-upmap namelijk niet zelf aan. Is de share bij het opstarten niet gekoppeld (NAS nog uit), dan bestaat de map niet, mislukt de back-up met een duidelijke melding en volgt na een uur een nieuwe poging. Zo komen je back-ups nooit stilletjes op de eigen schijf van de container terecht.

**9. Laten meestarten.** Zet in Proxmox bij de container **Options → Start at boot** op **Yes**. Maak ook een Proxmox-back-up van de container (Datacenter → Backup) als je de hele installatie wilt kunnen terugzetten.

**Bijwerken:** zet de nieuwe zip in de container (bijvoorbeeld in `/root`) en draai:

```
cd /opt/modelarr
sh update.sh --upgrade /root/modelarr.zip
```

Database en thumbnails blijven bewaard. Je bestaande `/etc/modelarr.env` wordt niet overschreven: voeg `BACKUP_DIR` daar zelf toe.

**Meldingen bij het koppelen van de share**

| Melding | Oorzaak en oplossing |
|---|---|
| `mount error(13): Permission denied` | De NAS weigert de inlog. Controleer met `cat -A /root/.smbcred` of er geen typefout, spatie of vreemd teken in staat. Typ als test het wachtwoord handmatig: `mount -t cifs //192.168.1.10/3d /mnt/3d-modellen -o username=GEBRUIKER,vers=3.0`. Werkt dat, dan zit de fout in het inlogbestand. Anders: controleer of het account op de Synology SMB mag gebruiken en rechten op de share heeft, en probeer `vers=3.1.1` of `vers=2.1`. |
| `mount error(22): Invalid argument` | Meestal een dubbele of onjuiste regel in `/etc/fstab`, of `mount -o remount` op een CIFS-koppeling. Verwijder de oude regel, `umount` en `mount -a`. |
| `Operation not permitted` | De feature SMB/CIFS staat niet aan (stap 2), of de container is unprivileged. |
| `mount: ... could not resolve address` | Controleer het IP-adres of de naam van de NAS en of de container netwerk heeft (`ping 192.168.1.10`). |
| De share is leeg na een herstart | De NAS stond nog niet aan toen de container opstartte. Draai `mount -a`; Modelarr ziet de share binnen een minuut terug. Voorkom het met `x-systemd.automount` in de fstab-regel (zie hieronder). |

**Share na een herstart**

Staat de NAS nog uit (of is het netwerk nog niet klaar) als de container opstart, dan zorgt `nofail` dat de container gewoon doorstart, maar zonder share: `/mnt/3d-modellen` is dan een lege map. Daarom:

1. **Gebruik `x-systemd.automount`** in de fstab-regel, zoals in stap 4. De share wordt dan gekoppeld zodra Modelarr de map opent, en bij een volgende poging opnieuw geprobeerd. Heb je al een oude regel zonder deze opties? Pas hem aan met `nano /etc/fstab` en draai daarna `systemctl daemon-reload`, `umount /mnt/3d-modellen` en `mount -a`.
2. **De service wacht op de netwerkshares.** `install-lxc.sh` zet `After=` en `Wants=remote-fs.target` in de service. Draai je Modelarr met Docker in een LXC (of op een andere Linux-host)? Laat Docker dan ook wachten:
   ```
   systemctl edit docker
   ```
   en zet erin:
   ```
   [Unit]
   After=remote-fs.target
   Wants=remote-fs.target
   ```
   Een Docker-container die gestart is terwijl de share er nog niet was, blijft namelijk de lege map zien. Herstel dat met `docker restart modelarr`.
3. **Modelarr waarschuwt zelf.** Is een root folder niet bereikbaar, of leeg terwijl er modellen bekend zijn, dan verschijnt er een rode balk bovenaan de app en een melding in de geschiedenis. Er wordt dan niets uit de bibliotheek verwijderd, en Modelarr kijkt elke minuut opnieuw. Zodra de share terug is, verdwijnt de melding vanzelf.
4. **Geef de NAS een vast IP-adres** (een statische DHCP-lease in je router), zodat het adres in de fstab-regel blijft kloppen.

## Configuratie
| Variabele | Standaard | Betekenis |
|---|---|---|
| `MODELS_DIR` | – | Standaard root folder(s), komma-gescheiden |
| `CONFIG_DIR` | `/config` (Docker) | Database, thumbnails en instellingen |
| `PORT` / `HOST` | `8765` / `0.0.0.0` | Poort en bind-adres |
| `AUTH_USER` / `AUTH_PASS` | – | Maakt bij de eerste start een beheerdersaccount aan (als er nog geen accounts zijn) |
| `MAX_FILE_MB` | `400` | Grotere bestanden krijgen geen thumbnail |
| `YIELD_TO_USERS` | `1` | `0` = de achtergrondtaak wacht nooit even als je de app gebruikt |
| `BACKUP_DIR` | `<config>/backups` | Map voor de dagelijkse back-ups (zie "Back-ups"); de instelling in de app gaat voor |
| `ALLOW_ORGANIZE` | – | `1` = hernoemen/verplaatsen toestaan voor de roots uit `MODELS_DIR` (standaard alleen indexeren) |

Overige instellingen (scaninterval, extensies, thumbnailgrootte, extra root folders, authenticatie,
API-sleutel) staan in de app onder **Instellingen**.

## Bambuddy-koppeling
Heb je [Bambuddy](https://github.com/maziggy/bambuddy) (zelf gehoste printbeheer voor Bambu Lab-printers)? Dan kun je het op twee manieren koppelen. Het is optioneel en staat uit zolang het adres of de sleutel leeg is.
1. Maak in Bambuddy onder **Instellingen → API Keys** een sleutel (je ziet hem maar één keer).
2. Vul in Modelarr onder **Instellingen → Algemeen → Bambuddy** het adres (bijv. `http://192.168.1.20:8000`) en de sleutel in. Klik op **Opslaan** en dan op **Verbinding testen**.
- **Model versturen:** open een `.3mf`-, `.gcode`- of `.stl`-model en klik op **↗ Naar Bambuddy…**. Kies **In bibliotheek zetten** of kies een printer en **In wachtrij zetten**. Er wordt nooit iets gestart: starten doe je zelf in Bambuddy. Alleen beheerders zien deze knop. **De wachtrij van Bambuddy neemt alleen geslicede bestanden aan** (`.gcode` of een 3MF met G-code erin, dus uit je slicer geëxporteerd als "gesliced"). Een STL of een niet-geslicede 3MF kun je wel in de bibliotheek zetten, maar niet in de wachtrij; Modelarr meldt dat vooraf.
- **Kleuren in de printers:** in het venster "Naar Bambuddy…" zie je na het kiezen van een printer welke spoelen er nu echt in zitten (AMS en externe spoel), met kleurnaam en materiaal. Dat komt uit de status van de printer in Bambuddy en werkt ook voor spoelen zonder RFID; het resterende gewicht is alleen bekend bij Bambu-RFID-spoelen. De lijst staat ook in de API: `GET /api/bambuddy/colors` (optioneel `?printer=ID`). De API-sleutel in Bambuddy heeft hiervoor het recht **Read Status** nodig.
- **Printgeschiedenis:** elke 30 minuten (of met **Nu synchroniseren**) wordt het printlogboek van Bambuddy overgenomen in het printlogboek van Modelarr. Een regel wordt gekoppeld aan het model met dezelfde naam, alleen als dat eenduidig is (bij twee modellen met dezelfde naam wordt de `.3mf` gekozen; blijven er dan nog meer over, dan wordt hij overgeslagen). Gelukt en mislukt komen binnen, met printer, gewicht, tijd en eventuele reden. Prints die nog bezig zijn of zijn afgebroken, en regels zonder bijpassend model, worden niet overgenomen; bij een volgende keer wordt het opnieuw geprobeerd. Een regel komt maar één keer binnen, ook als je hem in Modelarr later verwijdert.
- **Verbruik en Spoolman:** Bambuddy houdt zelf het filamentverbruik bij. Haal je prints binnen via de synchronisatie, laat Modelarr dan **geen** verbruik meer van een spoel aftrekken, anders trek je het twee keer af.
- **Sleutel:** de API-sleutel wordt in de database van Modelarr opgeslagen (net als de eigen API-sleutel) en nooit teruggestuurd naar de browser. Met **Sleutel wissen** zet je de koppeling uit.

## Hoe nieuwe bestanden worden opgenomen
- Live bestandswachter (inotify) op elke root folder op een lokale schijf, met 3 sec debounce. Op netwerkshares (NFS/SMB/CIFS)
  wordt de wachter niet gebruikt: die levert toch geen events voor wijzigingen van andere computers, en het opzetten ervan
  over een grote share duurde minuten voordat de website beschikbaar was.
- Extra scan elke N minuten (standaard 5): zo worden NFS/SMB-shares bijgehouden, want die geven geen events door
  voor wijzigingen die vanaf andere computers komen.
- Nieuwe of gewijzigde bestanden worden pas opgenomen als ze 10 sec oud zijn én hun grootte 10 sec gelijk is gebleven
  (kopieën via SMB/NFS behouden vaak de oude datum). Een eerste import duurt daarom minstens ±10 sec langer.
- Symlinks worden niet gevolgd.
- Verplaatst/hernoemd buiten de app (zelfde grootte + datum) = zelfde model, categorieën blijven.
- Is een root folder leeg of offline, dan wordt er niets uit de bibliotheek verwijderd. Je ziet dan een rode balk bovenaan de app en een regel in de geschiedenis; Modelarr kijkt elke minuut opnieuw en de melding verdwijnt zodra de map terug is.
- Kan een submap tijdens de scan niet gelezen worden (share hapert, geen rechten), dan blijven de modellen in die map staan en zie je ook een melding.
- Mappen die beginnen met `.`, `@` of `#` (o.a. Synology `@eaDir`, `#recycle`) worden overgeslagen.
- Opstarttijd controleren: `journalctl -u modelarr | grep -E "Database gereed|Webserver start|Bestandswachter"` (Docker: `docker logs modelarr`).

## Zoeken en filters
Het zoekveld zoekt in bestandsnaam, weergavenaam, categorie, extensie, map en 3MF-info (ontwerper, titel, printer...).
Meerdere woorden moeten allemaal kloppen. Beperk tot een veld met een prefix: `naam:` `ext:` `cat:` `map:` `ontwerper:` `kleuren:` (aantal kleuren, bijv. `kleuren:3`),
bijvoorbeeld `rack ext:3mf cat:server map:lab` of `cat:"10 inch"`.
Daarnaast filters op categorie, formaat en: zonder preview, recent toegevoegd (standaard 7 dagen) en grote bestanden
(standaard vanaf 50 MB); beide drempels staan onder Instellingen → Mediabeheer.

## Duplicaten
Onder **Duplicaten** staan bestanden die dubbel in je bibliotheek zitten:
- **Identiek:** exact dezelfde inhoud (hash), ook onder een andere naam of in een andere map. Alleen bestanden met dezelfde grootte
  worden vergeleken, dus er wordt weinig gelezen. Bij een nieuw dubbel bestand komt er een melding in Activiteit → Geschiedenis.
- **Mogelijk dezelfde mesh:** zelfde aantal driehoeken en afmetingen (bijv. STL én 3MF van hetzelfde model). Dat is een aanwijzing, geen bewijs.
Met "Naar prullenbak" verplaats je een bestand naar `<root folder>/.prullenbak`; er wordt niets definitief gewist en de laatste kopie
van een groep kan nooit verplaatst worden. In de bibliotheek heb je een filter "Dubbele bestanden" en een ⧉-label op de kaartjes.

### Modellen uit de bibliotheek naar de prullenbak

Selecteer modellen in de bibliotheek (vinkjes, Shift+klik voor een bereik, of "Alles selecteren") en kies **🗑 Naar prullenbak**. Je krijgt eerst een bevestiging met het aantal. De bestanden gaan naar `<root folder>/.prullenbak` en worden niet definitief gewist. Terughalen doe je door ze uit die map te verplaatsen en een scan te starten. Dit werkt alleen voor roots waar "verplaatsen" aan staat (Instellingen → Mediabeheer); modellen in een zip worden overgeslagen. Wat niet lukt blijft geselecteerd, met de reden in de melding. Het logboek (Activiteit → Geschiedenis) noteert elk verplaatst bestand. De knoppen "In categorie zetten" en "Uit categorie halen" daarnaast raken de bestanden zelf niet.

**Rechtsklikmenu:** klik met de rechtermuisknop op een model (kaartje of tabelrij) voor dezelfde acties: in categorie zetten, uit categorie halen, favoriet, niet favoriet en naar prullenbak. Staat het model in je selectie, dan geldt het menu voor de hele selectie, anders alleen voor dat model. Na elke actie wordt de selectie gewist. Alleen wat bij het verplaatsen naar de prullenbak niet lukte, blijft geselecteerd. Gasten krijgen het gewone browsermenu. Op een telefoon of tablet krijg je hetzelfde menu door een model ongeveer een halve seconde ingedrukt te houden; tik op "In categorie zetten" of "Uit categorie halen" om de categorieën te zien.

## Veel modellen indelen: mappen, regels en snel selecteren

**Instellingen → Automatisch indelen** (ook bereikbaar via een link op de pagina Categorieën):

- **Categorieën uit mappen.** Elke map op het hoogste niveau van je root folders kan een categorie worden. Je ziet per map het aantal modellen en of ze al zijn ingedeeld. Vink de mappen aan die je wilt (of kies "Alles kiezen" / "Alleen nog niet ingedeelde"), pas zo nodig de categorienaam aan (een bestaande categorie mag ook) en kies **Toepassen**. Alle modellen in die map, ook in submappen, komen in de categorie. Dit haalt nooit iets weg en kan veilig opnieuw. Modellen die direct in een root folder staan hebben geen map en doen niet mee. Dit onthoudt de map: er komt een regel "map is …" bij, zodat **nieuwe bestanden in die map (ook in submappen) bij de volgende scan dezelfde categorie krijgen**. Mappen die je met een eerdere versie al had ingedeeld (met een categorie met dezelfde naam als de map) krijgen die regel bij de update vanzelf; bij een andere categorienaam deel je de map nog één keer opnieuw in. Verwijder je de regel onder Regels, dan stopt het automatisch indelen voor die map.
- **Regels.** "Pad bevat", "naam bevat" of "extensie is" een tekst, dan hoort het model in een categorie. Nieuwe bestanden krijgen de categorie automatisch bij de scan. Met **Alle regels nu toepassen** gaan ook de bestaande modellen mee. Bij elke regel zie je hoeveel modellen erbij passen en hoeveel nog niet zijn ingedeeld. Het pad telt vanaf de root folder met / tussen de mappen, bijvoorbeeld `10 inch rack/`. Een regel haalt nooit een categorie weg.

**Sneller selecteren in de bibliotheek** (voor beheerders):

- Zodra er iets geselecteerd is, selecteert een klik op een kaartje of rij (niet alleen op het vinkje). **Dubbelklik** opent het model.
- **Ctrl/Cmd+klik** start een selectie, **Shift+klik** selecteert alles tussen twee modellen.
- **Sleep een kader** over de modellen om ze te selecteren. Met Ctrl, Cmd of Shift erbij voeg je toe aan de bestaande selectie. Bij de boven- of onderrand scrolt de lijst vanzelf mee.
- **Ctrl/Cmd+A** selecteert alles wat in het huidige filter past (ook op andere pagina's). **Escape** of een klik naast de modellen wist de selectie.

## Veilig standaard
De app indexeert standaard alleen: bestanden hernoemen of naar de prullenbak verplaatsen moet je per root folder aanzetten
(Instellingen → Mediabeheer, of `ALLOW_ORGANIZE=1`). De weergavenaam, notities enzovoort in de database kun je altijd wijzigen.
Zet je volume bovendien op `:ro`, dan kan de app helemaal niets aan je bestanden doen.
Staat de config-map (met de SQLite-database) op een netwerkshare (NFS/SMB), dan waarschuwt de app: SQLite is daar onbetrouwbaar.

## Notities, favorieten, bron en printstatus
Per model: favoriet (★), bronlink, notities en printstatus (onbekend / te printen / geprint). Alles is doorzoekbaar
(`notitie:` en `bron:`) en filterbaar; voor meerdere modellen tegelijk gebruik je de selectie in de bibliotheek.

## Thumbnails
- **3MF, FCStd en G-code:** de ingebouwde afbeelding van het bestand wordt gebruikt als die er is (bijv. het plaatbeeld van Bambu Studio);
  anders rendert de app zelf. Via Instellingen kun je altijd zelf laten renderen.
- **Eigen opname:** draai een model in het detailvenster en kies "Weergave als thumbnail". Dat blijft staan tot je "Thumbnail opnieuw" kiest
  of het bestand verandert.
- **Rustig op een NAS:** de achtergrondtaak draait met lage prioriteit, wacht even als je de app gebruikt, kan een pauze tussen
  thumbnails inlassen en kan onder Activiteit → Wachtrij gepauzeerd worden.

## Meer bestandstypen
Naast de modelformaten met preview worden standaard ook CAD- en projectbestanden geïndexeerd (STEP, F3D, Blender, SketchUp, SolidWorks,
FBX, DXF...). Die staan zonder 3D-preview in de bibliotheek, zijn doorzoekbaar en doen mee in de dubbelencheck.
Zip, rar en 7z staan niet standaard aan: voeg ze toe onder Instellingen → Mediabeheer → Bestandsextensies als je pakketten als geheel wilt catalogiseren.

## 3MF-informatie
Uit 3MF-bestanden worden titel, ontwerper, programma, licentie en aanmaakdatum gelezen, plus (als aanwezig) printer, laaghoogte,
nozzle, filamenttype en bij Bambu Studio ook printtijd en filamentverbruik. Zichtbaar in het detailvenster en doorzoekbaar.

**Kleuren:** bij een gesliced Bambu/Orca-project telt de app de filamenten die echt gebruikt worden (met verbruik). Bij een project dat nog niet gesliced is telt hij de filamenten waaraan objecten zijn toegewezen; kleuren die alleen met verfpenseel op delen van een object zijn aangebracht, tellen dan niet mee. Je ziet de kleurvlakjes en het aantal in het detailvenster, zoekt met `kleuren:3` en filtert met **Meerkleurig (2+ kleuren)**. Bij de eerste start na het bijwerken worden alle 3MF-bestanden eenmalig opnieuw gelezen (op de achtergrond); een 3MF zonder kleurinformatie toont niets.

## Printers en "past dit op mijn printer?"
Onder Instellingen → Printers voer je je printers in met de bedgrootte (X, Y, Z in mm); er zijn voorinstellingen voor Bambu Lab
(A1 mini, A1, P1P, P1S, X1 Carbon, P2S, H2S; controleer de maten altijd met je eigen printer, de H2D ontbreekt omdat bronnen verschillen).
Elk model toont dan "Past op: ✓ P1S · ✗ A1 mini" en in de bibliotheek is er een filter "Past op …". Een model mag 90° gedraaid worden;
de controle gebruikt de afmetingen van het hele model, bij een 3MF met meerdere onderdelen dus van de hele indeling.

## Zip-bestanden
Modellen in zip-bestanden worden doorzocht en gepreviewd zonder uitpakken (alleen dat ene onderdeel wordt tijdelijk uitgepakt). Ze staan in de
bibliotheek met het label ZIP, met thumbnail, afmetingen, categorieën, notities en meedoen in de dubbelencheck (ook tegen losse kopieën).
Een zip die je verplaatst of hernoemt behoudt zijn modellen; wijzigt de zip, dan blijven bestaande onderdelen hun categorieën houden.
Beperkingen: alleen `.zip` (geen rar/7z), onderdelen groter dan `MAX_FILE_MB` worden overgeslagen, en een onderdeel uit een zip kun je niet
hernoemen of naar de prullenbak verplaatsen (wel de weergavenaam wijzigen). Uitzetten kan onder Mediabeheer; dan verdwijnen die modellen uit de bibliotheek.

## Meerdere platen (Bambu Studio / OrcaSlicer)
Heeft een 3MF meerdere platen, dan verschijnen in de viewer tabbladen "Alles / Plaat 1 / Plaat 2 …" en kun je het printlogboek per plaat bijhouden.
PrusaSlicer-bestanden hebben geen platen.

## Printlogboek en Spoolman
Per model log je prints (gelukt of mislukt, printer, plaat, gewicht, notitie). Een geslaagde print zet het model op "geprint"; de bibliotheek heeft
het filter "Eerder mislukt". Heb je Spoolman, vul dan het adres in onder Instellingen → Algemeen (in Docker: de containernaam of het NAS-adres, bijv.
`http://spoolman:7912`). Bij het loggen kies je een spoel en wordt het verbruik (gram) in Spoolman afgetrokken. Dat gebeurt eerst: lukt het niet,
dan wordt er niets gelogd. Een logregel verwijderen draait het verbruik in Spoolman niet terug.

## Openen in je slicer
- **Openen in Bambu Studio** (of OrcaSlicer / PrusaSlicer, te kiezen onder Algemeen): de app maakt een tijdelijke, ondertekende downloadlink (10 minuten, zonder
  wachtwoord in de link) en geeft die door aan de slicer, die het bestand zelf ophaalt. Het adres van de app moet dus vanaf je computer bereikbaar zijn.
  Of Bambu Studio zo'n adres op je lokale netwerk accepteert, is niet te testen zonder de slicer; werkt het niet, gebruik dan Download of de volgende optie.
- **Openen met standaardprogramma**: verschijnt alleen als je browser op dezelfde computer draait als de app (bijv. de Windows-versie); het bestand gaat dan
  open met het programma dat Windows/macOS daarvoor kiest.

## Formaten
Thumbnails en 3D-weergave: STL, 3MF (incl. slicer-bestanden en meerdere platen), OBJ, PLY, GLB/GLTF.
OBJ/GLB/GLTF worden als Y-up gelezen, STL/3MF/PLY als Z-up.

## Verhuizen tussen Windows, Docker en Synology
De app kent een map alleen onder het pad zoals hij het zelf ziet: `\\192.168.1.5\3d` op Windows, maar `/models` in Docker (waar je zelf `/volume1/3d` aan koppelt via `/volume1/3d:/models`).
Het Synology-pad `/volume1/3d` komt dus nooit in de app voor. Alle paden in de database zijn daarom per platform anders; de rest (thumbnails als gewone PNG-bestanden, categorieën, notities, printlogboek, accounts) is overal hetzelfde.
- **Meest eenvoudig:** laat één exemplaar draaien (bijvoorbeeld Docker op de NAS) en gebruik de browser op je Windows-pc. Dan is er één database en hoef je niets te verhuizen. "Openen in Bambu Studio" werkt ook vanaf je pc.
- **Een bestaande bibliotheek verhuizen** (bijvoorbeeld van Windows naar Docker): stop beide, kopieer `library.db` en de map `thumbs` uit de map `config` naar het `config`-volume van de nieuwe plek en start de app.
  De oude root staat dan als "niet bereikbaar" (er wordt niets verwijderd). Kies bij die root onder Instellingen → Mediabeheer **Pad wijzigen** en geef het pad zoals de nieuwe plek het ziet (bijvoorbeeld `/models/10 inch rack`).
  De app toont hoeveel bestanden hij daar vindt en vraagt om bevestiging. Alle modellen houden hun categorieën, notities, favorieten, printlogboek en thumbnails, ook de eigen opnames. Schuine strepen worden automatisch omgezet (`\` naar `/` en terug).
- **Heeft de nieuwe plek de map al gescand** (bijvoorbeeld via `MODELS_DIR`)? Dan staan dezelfde bestanden er twee keer in. Geef de oude root bij **Pad wijzigen** hetzelfde pad: de app voegt ze samen en de modellen met je gegevens vervangen de verse dubbele ingangen.
- **Wijzigingstijden:** Windows (SMB) en Linux ronden de wijzigingstijd van een bestand soms net anders af. De app laat verschillen tot 2 seconden daarom door en maakt geen thumbnails opnieuw.
- **Niet doen:** twee exemplaren op dezelfde database laten draaien, of de database op een netwerkshare zetten. Houd de database lokaal bij de app. Staat Spoolman op `localhost`, pas dan het adres onder Instellingen → Algemeen aan.

## Gebruikers en toegang
Zonder accounts kan iedereen met toegang tot het adres alles (de app waarschuwt daarvoor). Maak onder Instellingen → Gebruikers eerst je eigen
**beheerdersaccount** aan; vanaf dat moment moet iedereen inloggen. Daarna kun je **gasten** toevoegen, bijvoorbeeld bekenden die je collectie mogen gebruiken:
- **Beheerder:** alles.
- **Gast (kijker):** de bibliotheek bekijken, zoeken en filteren, en (per gast in te stellen) modellen downloaden en openen in de slicer. Een gast kan niets
  wijzigen of beheren, en ziet geen notities, printlogboek, favorieten of de bestandspaden op je schijf. Zonder download-recht ziet een gast alleen de thumbnails.
  Downloads van gasten komen met hun naam in Activiteit → Geschiedenis.
- **Uploaden:** per gast in te stellen (kolom "Uploaden"; beheerders mogen altijd). Wie mag uploaden ziet in de bibliotheek de knop **⬆ Uploaden**: kies de root folder en map (of maak een nieuwe map), vink de categorieën aan en kies een of meer modellen. Een bestand met een bestaande naam wordt nooit overschreven (er komt (2) achter), alleen toegestane bestandstypen en bestanden tot `MAX_FILE_MB` worden aangenomen, en er wordt nooit buiten de root folder geschreven. De root folder moet beschrijfbaar zijn (niet `:ro` gekoppeld). Het model verschijnt na de eerstvolgende scan (enkele seconden) met de gekozen categorieën; uploads staan in Activiteit → Geschiedenis. Een gast met upload-recht kan verder niets wijzigen en ziet geen paden op je schijf.
- **E-mailadres (optioneel):** bij een account kun je een e-mailadres opslaan; inloggen kan dan ook met dat adres. De app verstuurt zelf geen e-mail (er is geen mailserver ingesteld).
- **Beveiliging:** wachtwoorden zijn versleuteld opgeslagen (minstens 8 tekens), na 5 foute pogingen is inloggen 10 minuten geblokkeerd (per adres), de sessiecookie
  is niet door scripts te lezen en verzoeken vanaf andere websites worden geweigerd. Wijzig je een wachtwoord of zet je een account uit, dan vervalt de lopende sessie direct.
  Je kunt de laatste beheerder niet verwijderen of degraderen; "Alle accounts verwijderen" zet het inloggen weer uit.
- **Op internet delen:** doe dat alleen via HTTPS (bijvoorbeeld de reverse proxy van je NAS), want zonder HTTPS reizen wachtwoorden onversleuteld.
  Achter een reverse proxy zien alle gebruikers hetzelfde adres, dus de blokkade na foute pogingen geldt dan voor iedereen samen.
- **Bestaande inlog:** een eerder ingestelde enkele inlog wordt bij de update automatisch een beheerdersaccount. `AUTH_USER`/`AUTH_PASS` maken bij de eerste start
  een beheerder aan als er nog geen accounts zijn. De API-sleutel (header `X-Api-Key`) geeft beheerdersrechten voor koppelingen; ondertekende downloadlinks blijven 10 minuten werken zonder inloggen.


## API en koppelingen (API-sleutel)

De API-sleutel staat onder **Instellingen → Algemeen** (daar maak je ook een nieuwe; de oude werkt dan niet meer). Stuur hem mee als header `X-Api-Key`. Daarmee kom je zonder inloggen bij de API, met **beheerdersrechten**. Behandel hem dus als een wachtwoord:

- Zet hem nooit in een link (`?apikey=` wordt bewust geweigerd) en deel hem niet.
- Voor verzoeken met de sleutel hoef je geen `X-Requested-With`-header mee te sturen.
- Gebruik hem alleen via je eigen netwerk of via https.

Alle antwoorden zijn JSON. Foutmeldingen hebben de vorm `{"error": "…"}`. In de voorbeelden is `nas:8765` het adres van Modelarr en `SLEUTEL` je API-sleutel.

**Lezen**

| Opdracht | Wat het doet |
|---|---|
| `GET /api/rev` | Korte status: aantal thumbnails in de wachtrij (`pending`), mislukt (`failed`), groepen duplicaten (`dups`) en de voortgang van een lopende scan (`scan`). Handig voor Home Assistant. |
| `GET /api/status` | Aantallen, root folders en gezondheidsmeldingen. |
| `GET /api/library?page=0&size=50` | Modellen, per pagina. Zonder `page` krijg je de hele lijst (bij tienduizenden modellen een groot antwoord). |
| `GET /api/history` | De laatste 300 gebeurtenissen (het logboek). |
| `GET /api/wanted` | Modellen waarvan de thumbnail is mislukt, met de reden. |
| `GET /api/duplicates` | Groepen dubbele bestanden. |
| `GET /api/file/<id>` | Het modelbestand zelf downloaden. |
| `GET /api/thumb/<id>.png` | De thumbnail. |

Bij `/api/library` kun je dezelfde zoek- en filterregels gebruiken als in de app: `q` (zoektekst met prefixen als `ext:3mf cat:server map:lab`), `cat` (categorie-id, `none` of `all`), `ext`, `flt` (`all`, `nopreview`, `recent`, `big`, `dup`, `fav`, `toprint`, `printed`, `failedprint` of `fit:<printer-id>`), `sort` (`name`, `added`, `size`), `page` (begint bij 0) en `size` (aantal per pagina, `0` = alles). Het antwoord bevat `models` (de pagina), `total` (aantal dat past), `all` (aantal in de bibliotheek), `pages` en `ids` (alle id's die passen).

**Wijzigen** (POST, met `Content-Type: application/json`)

| Opdracht | Body |
|---|---|
| `POST /api/models/<id>` | Een of meer van: `display` (weergavenaam), `notes`, `favorite` (true/false), `printed` (`""`, `"toprint"`, `"printed"`), `source_url`, `filename` (alleen als hernoemen aan staat voor die root). |
| `POST /api/models/bulk` | `{"model_ids": [1,2,3], "favorite": true}` en/of `"printed": "toprint"`. |
| `POST /api/categories` | `{"name": "Rack"}`, geeft het `id` terug. |
| `POST /api/assign` | `{"model_ids": [1,2,3], "category_id": 4, "action": "add"}` (of `"remove"`). |
| `POST /api/models/trash` | `{"ids": [5,6]}`: verplaatst dubbele bestanden naar `.prullenbak` (nooit de laatste kopie). |
| `POST /api/tasks/scan/run` | Scan starten. Andere taken: `rebuild` (alle thumbnails opnieuw), `backup`, `thumbcheck`. |
| `POST /api/wanted/retry` | `{}` probeert alle mislukte thumbnails opnieuw, of `{"ids": [..]}`. |

**Voorbeelden**

```
# eerste 50 favoriete modellen met "rack" in de naam
curl -H "X-Api-Key: SLEUTEL" "http://nas:8765/api/library?page=0&size=50&q=rack&flt=fav"

# model 12 als favoriet markeren en een notitie toevoegen
curl -X POST -H "X-Api-Key: SLEUTEL" -H "Content-Type: application/json" \
     -d '{"favorite": true, "notes": "Printen in PETG"}' http://nas:8765/api/models/12

# categorie 3 aan een aantal modellen toevoegen
curl -X POST -H "X-Api-Key: SLEUTEL" -H "Content-Type: application/json" \
     -d '{"model_ids": [12, 13, 14], "category_id": 3, "action": "add"}' http://nas:8765/api/assign

# scan starten en de voortgang volgen
curl -X POST -H "X-Api-Key: SLEUTEL" http://nas:8765/api/tasks/scan/run
curl -H "X-Api-Key: SLEUTEL" http://nas:8765/api/rev
```

Python:

```python
import requests
api = "http://nas:8765"; h = {"X-Api-Key": "SLEUTEL"}
st = requests.get(f"{api}/api/rev", headers=h).json()
print(st["pending"], "thumbnails in de wachtrij")
```

Home Assistant (`configuration.yaml`):

```yaml
sensor:
  - platform: rest
    name: Modelarr thumbnails te doen
    resource: http://nas:8765/api/rev
    headers: {X-Api-Key: SLEUTEL}
    value_template: "{{ value_json.pending }}"
    scan_interval: 60
```

Wat hier niet staat (roots, printers, gebruikers, instellingen) kan ook, maar is bedoeld voor de app zelf en kan van versie tot versie veranderen. Wil je dat gebruiken, kijk dan in `app.py` bij de regels `@app.get` en `@app.post`.

## Back-ups
Elke dag maakt Modelarr een kopie van `library.db`. Je bepaalt zelf **waar** die komt, en de back-ups gaan altijd naar die map.

**De map instellen** (kies één van de twee):
- In de app: Instellingen → Mediabeheer → **Back-upmap**. Typ een volledig pad zoals de app het ziet (`/backups`, `/mnt/back-ups/modelarr` of `D:\Back-ups\Modelarr`), of kies een map met **Kiezen…**. De app controleert of hij in de map kan schrijven en maakt meteen een eerste back-up, zodat je direct ziet dat het werkt.
- Met de omgevingsvariabele `BACKUP_DIR` (in `docker-compose.yml`, `/etc/modelarr.env` of `start-windows.bat`). Dat is de standaard; de instelling in de app gaat voor. Maak je het veld in de app leeg, dan geldt weer `BACKUP_DIR`.
- Zonder beide: de map `backups` in je config-map.

Kies bij voorkeur een map **buiten** de config-map, op een andere schijf of op de NAS: een back-up die op dezelfde schijf staat als het origineel, valt samen met die schijf weg. In Docker is het pad een pad in de container: koppel de map als volume (`/mnt/back-ups/modelarr:/backups`) en gebruik `/backups`.

**Gedrag:**
- Altijd in de gekozen map. Is die niet bereikbaar (bijvoorbeeld een NAS die uit staat of een share die niet gekoppeld is), dan mislukt de back-up met een melding in Instellingen → Mediabeheer en onder Systeem → Taken, en volgt na een uur een nieuwe poging. De app schrijft **nooit stilletjes naar een andere map**.
- Een ontbrekende map wordt niet door de geplande back-up aangemaakt, zodat er geen lege map op de verkeerde schijf ontstaat. Maak de map zelf aan, terwijl de share gekoppeld is. Alleen als je de map in de app invult, wordt hij zo nodig aangemaakt. De standaardmap `config/backups` maakt zichzelf aan.
- Staat de back-upmap binnen een root folder, laat de mapnaam dan met een punt beginnen (bijvoorbeeld `/mnt/3d-modellen/.back-ups`): zulke mappen worden niet gescand. De mapkiezer bij **Kiezen…** toont mappen met een punt wél; je kunt het pad ook gewoon intypen. Een nieuwe map wordt aangemaakt als het pad bestaat en je er mag schrijven. Is de share alleen-lezen (`ro`) gekoppeld of mag het account er niet schrijven, dan krijg je "niet beschrijfbaar".
- Een back-up wordt eerst als tijdelijk bestand weggeschreven en pas daarna hernoemd. Een verbinding die halverwege wegvalt, laat dus nooit een halve back-up achter die voor echt kan doorgaan. De database wordt eerst lokaal gekopieerd, zodat SQLite nooit direct op een netwerkshare schrijft.
- Het aantal bewaarde back-ups stel je in bij Instellingen → Mediabeheer (standaard 7). De oudste in die map worden opgeruimd; andere bestanden in de map blijven onaangeroerd.
- Handmatig kan met **Nu back-uppen** (Instellingen → Mediabeheer) of onder Systeem → Taken.
- Optioneel (Instellingen → Mediabeheer) gaan de thumbnails mee als `library-<datum>-thumbs.zip`.

In de database staat alles wat de app van je modellen weet (categorieën, notities, favorieten...), plus de inlog en API-sleutel: behandel een back-up als gevoelig. Je modelbestanden en je compose-bestand zitten er niet in.

**Terugzetten:** stop de app, kopieer de gewenste back-up naar `library.db` in de config-map en verwijder `library.db-wal` en `library.db-shm` als die er staan. Start de app weer.
- Docker: `docker compose stop`, kopieer naar `config/library.db`, `docker compose start`.
- LXC: `systemctl stop modelarr`, `cp /mnt/back-ups/modelarr/library-<datum>.db /var/lib/modelarr/library.db`, `rm -f /var/lib/modelarr/library.db-wal /var/lib/modelarr/library.db-shm`, `systemctl start modelarr`.
- Windows: sluit de app, kopieer naar `config\library.db`, start de app.

Wil je ook de thumbnails terug, pak dan het bijbehorende zip-bestand uit in de map `thumbs` van de config-map. Doe je dat niet, dan is dat geen probleem: bij het opstarten (en na elke scan) controleert de app of elke thumbnail bestaat en bij het juiste model hoort, en laat ontbrekende of verkeerde thumbnails vanzelf opnieuw maken. Eigen opnames uit de viewer gaan alleen terug als je de thumbnails uit de back-up uitpakt.

Zet de back-upmap ook in een back-up buiten het huis (bijvoorbeeld Hyper Backup op een Synology): een back-up die op dezelfde locatie staat als het origineel, helpt niet bij brand of diefstal.

## Taal (Nederlands / English)
Linksonder in de navigatie (en op de inlogpagina) staan de knoppen NL en EN. De keuze wordt per browser onthouden; zonder keuze volgt de app de taal van de browser.
- Nederlands is de brontaal. De Engelse tekst staat in `static/i18n-en.js` (Nederlandse tekst, Engelse tekst) en wordt in de browser op de pagina toegepast, ook op meldingen van de server. Namen van modellen, categorieën en notities worden nooit vertaald.
- De pagina Logs blijft Nederlands. Een tekst die niet in de woordenlijst staat, blijft Nederlands.
- **Een tekst toevoegen:** zet hem in `static/i18n-en.js` onder `exact` (hele tekst), `phrases` (zinsdeel naast een ingevulde waarde) of `patterns` (reguliere expressie voor een andere woordvolgorde). `node tests/i18n_test.mjs` en `python tests/test_i18n_server.py` melden welke zichtbare tekst nog geen vertaling heeft.

## Tests
Alles in één keer: `python tests/run_all.py` (vereist node en de pakketten uit requirements.txt; duurt enkele minuten). Losse onderdelen:
- `python tests/<naam>.py` voor de Python-tests (database, scanner, accounts, verhuizen van paden, printlogboek, zip en platen, back-up).
- `node tests/ui_test.mjs` voert de echte `static/app.js` uit met een nagebouwde pagina en server en draait de controles in `tests/ui/` (optioneel: `node tests/ui_test.mjs <deel van de bestandsnaam>`).
- `node tests/i18n_test.mjs` en `python tests/test_i18n_server.py` voor de Engelse versie.

## Sneller thumbnails maken (NAS)

Thumbnails worden op de achtergrond gemaakt. Op een trage NAS kan dat met tienduizenden bestanden uren tot dagen duren. Drie knoppen:

- `THUMB_WORKERS=3` (omgevingsvariabele, standaard 1): meerdere thumbnails tegelijk. Op een DS423 (4 cores, 2 GB RAM) is 3 veilig; hoger heeft weinig zin en kost geheugen.
- `THUMB_MEM_MB=4096` (standaard 4096, 0 = geen limiet): geheugenlimiet per model. Thumbnails, 3MF-info en de 3D-viewer draaien in een apart hulpproces (`renderproc.py`); een enorm model kan daardoor nooit meer de hele server of container laten vollopen. Wordt de limiet overschreden, dan krijgt alleen dat model de melding "Te weinig geheugen om dit model te verwerken". Met `THUMB_WORKERS=3` heb je tot 3 × deze limiet nodig.
- `THUMB_TIMEOUT=600` (seconden per model, 0 = geen limiet) en `THUMB_ISOLATE=0` (hulpproces uitzetten; alles draait dan in de app zelf, alleen voor foutzoeken).
- `THUMB_MAX_TRIS=250000` (standaard): modellen met meer driehoeken worden voor de thumbnail uitgedund. Een thumbnail is 384 px, dus het verschil is niet te zien, maar een model van 1 miljoen driehoeken is zo ruim 4x sneller.
- Laat de pc het zware werk doen: draai Modelarr lokaal op de hele share, kopieer daarna de `config`-map naar de NAS en gebruik onder Mediabeheer "Pad wijzigen". De thumbnails blijven geldig.

## Bijwerken

Zet de nieuwe zip naast je `docker-compose.yml` (of in je Downloads-map) en draai in die map:

```
sh update.sh                      # zoekt zelf de nieuwste modelarr*.zip
sh update.sh pad/naar/nieuw.zip   # of geef de zip op
```

Het script vervangt de programmabestanden, laat `config/` (database, thumbnails, instellingen) en je eigen `docker-compose.yml` ongemoeid en bouwt de container opnieuw. In een LXC draai je het vanuit `/opt/modelarr` (`cd /opt/modelarr && sh update.sh --upgrade /root/modelarr.zip`). Op een Synology: SSH of een geplande taak ("Door gebruiker gedefinieerd script", als root). Zonder SSH: pak de zip uit via File Station, overschrijf alles behalve `config` en `docker-compose.yml`, en kies in Container Manager → Project → Opnieuw opbouwen.

### Grote bibliotheken

Zoeken, filteren, sorteren en pagineren gebeurt op de server: de browser krijgt alleen de pagina die je ziet (bijvoorbeeld 100 modellen) en niet de hele lijst. Dat houdt het geheugen laag en de weergave snel, ook bij tienduizenden modellen. De lijst op de server wordt onthouden tot er iets verandert.

### Onderdelen bijwerken (Docker en LXC)

`sh update.sh --upgrade` werkt naast de programmabestanden ook de onderdelen bij. Het script herkent zelf waar het draait:

- **Docker** (map met `docker-compose.yml`): bouwt opnieuw met `--pull --no-cache`, dus met de nieuwste Python-basisimage en de nieuwste pakketten. Zonder `--upgrade` hergebruikt Docker de oude lagen.
- **LXC** (`/opt/modelarr`, met `venv`): werkt de Python-pakketten bij (`pip install -U`) en herstart de service. Draai het script daar vanuit `/opt/modelarr`. Het besturingssysteem werk je bij met `apt-get update && apt-get -y upgrade`. `sh install-lxc.sh` opnieuw draaien kan ook en is veilig.

De meldingen "Running pip as the 'root' user" en "A new release of pip is available" tijdens het bouwen zijn alleen mededelingen, geen fouten. In deze versie zijn ze uitgezet.

## Licentie
MIT, zie [LICENSE](LICENSE).

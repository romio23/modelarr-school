# Modelarr (server version)

> This app was built with the help of [Claude](https://claude.ai/) (Anthropic). Yes, I vibe-coded it.

> This is the English version of the documentation. The Dutch original is [README.md](https://github.com/romio23/modelarr/blob/main/README.md); if the two ever differ, the Dutch one is leading. The app itself can be switched to English with the **EN** button at the bottom left of the navigation.

Modelarr manages your 3D models the way Sonarr and Radarr manage your movies and series.

Root folders, a live file watcher, automatic thumbnails, categories, queue/history, tasks, logs and a status page.

## Windows (without Docker or Proxmox)
1. Install Python 3.10+ from python.org (tick "Add python.exe to PATH").
2. Open `start-windows.bat` with Notepad and fill in `MODELS_DIR` (e.g. `D:\3D` or `\\nas\models`). Then double-click it.
   The first time, the components are installed; the browser opens by itself at http://127.0.0.1:8765.
3. Start automatically at login: `autostart-aan.bat` (turn off with `autostart-uit.bat`).

Network shares: use a UNC path (`\\nas\models`: server *and* share) instead of a drive letter; a scheduled task does not always see mapped drive letters.
You can type or paste such a path, including the quotes from "Copy as path" in File Explorer: in the folder picker, or directly in the field under Settings → Media management.
If a share is already mapped to a drive letter, the folder picker shows the matching network path and you can choose it with one click.
The Windows account the app runs under must have access to the share. If the share asks for credentials, store them in Windows: `cmdkey /add:nas /user:username /pass:password`.
If you want to open the app from other devices, set `HOST=0.0.0.0` *and* create an account (Settings → Users); Windows then asks for firewall permission.
Database, thumbnails and logs are in the `config` folder next to the app. If you want the daily backups on another disk, set `BACKUP_DIR` in `start-windows.bat` or set the folder under Settings → Media management (see "Backups"). Not tested on Windows by the developer: report problems with the log file `config\modelarr.log`.

## Installation on Docker or Proxmox

Windows is covered above. For the other platforms there are step-by-step guides:

1. **Docker on a Synology** (Container Manager)
2. **Docker on a regular Linux server or PC**
3. **Proxmox LXC** (without Docker)

What applies to all three:

- Modelarr uses port **8765**, not 5000 (Synology DSM uses that one).
- Paths in the app are always paths **as the app sees them**: `/models` in Docker, `/mnt/3d-modellen` in the LXC. Never the path on your NAS.
- Keep the database (`config`) **local** to the app, not on a network share. Your backups, on the other hand, are best kept somewhere else (see "Backups").
- Run only one instance at a time on the same database.

### Docker on a Synology (Container Manager)

Written for DSM 7.2 and Container Manager; not tried on every DSM version. The names of menus can differ slightly per version.

**Preparation**

1. Install **Container Manager** from the Package Center.
2. Make sure you have three folders (Control Panel → Shared Folder):
   - your model folder, for example `3D` (path `/volume1/3D`);
   - a folder for the program, for example the shared folder `docker` with the folder `modelarr` inside it (path `/volume1/docker/modelarr`);
   - a folder for the backups, for example the shared folder `Backups` with the folder `modelarr` inside it (path `/volume1/Backups/modelarr`). Preferably choose another volume or an external disk for this, so a backup is not on the same disk as the original.
3. Look up the user ID that Modelarr will use. Turn on SSH (Control Panel → Terminal & SNMP), log in and type `id yourusername`. Note the `uid` and `gid` (for example `1026` and `100`).
4. Give that user permissions (Control Panel → Shared Folder → the folder → Edit → Permissions):
   - model folder: **read**; only **read/write** if you want Modelarr to rename files or move them to the trash;
   - `docker`: **read/write** (the database and thumbnails go in `docker/modelarr/config`);
   - `Backups`: **read/write**.

**Installing**

5. Upload `modelarr.zip` with File Station to `docker/modelarr` and choose right-click → **Extract**. The file `docker-compose.yml` must be directly in `/volume1/docker/modelarr`. If it ended up in an extra folder `modelarr`, move the contents up one level.
6. Open `docker-compose.yml` and change it (remove the `#` where shown):

   ```yaml
   user: "1026:100"                 # uid:gid from step 3
   environment:
     - TZ=Europe/Amsterdam
     - MODELS_DIR=/models
     - BACKUP_DIR=/backups          # the daily backups go here
     - THUMB_WORKERS=3              # DS423: 3 is safe
   volumes:
     - ./config:/config
     - /volume1/3D:/models          # add :ro if the app must not change anything
     - /volume1/Backups/modelarr:/backups
   ```

7. Open Container Manager → **Project** → **Create**. Give it the name `modelarr`, choose `/volume1/docker/modelarr` as the path and let DSM use the existing `docker-compose.yml`. Building and starting takes a few minutes. Via SSH this works too: `cd /volume1/docker/modelarr && sudo docker compose up -d --build`.
8. Open `http://<ip-of-the-nas>:8765`. Because of `MODELS_DIR=/models` your model folder is already a root folder and the first scan starts. With tens of thousands of models this takes hours, mostly the thumbnails; see "Faster thumbnails (NAS)".
9. Create an account (Settings → Users) if you also use Modelarr from outside your own device.

**Checking**

- Settings → Media management → **Backup folder** shows `/backups`. Click **Back up now** and check in File Station whether a `library-….db` is in `Backups/modelarr`.
- If you see the message "Backup folder is not writable", give the user from step 3 write permission on `Backups`.
- Also put your backup folder in a Hyper Backup task to an external disk or the cloud, so you do not have a backup that only exists on the NAS itself.

**Updating:** see "Updating". Note: `update.sh` does not overwrite your own `docker-compose.yml`. If Modelarr is already running, add the `BACKUP_DIR` line and the `/backups` volume yourself and rebuild.

### Docker on a regular Linux server or PC

For a Linux server or a VM with Docker, for example Ubuntu or Debian.

1. **Install Docker.** Follow the guide for your system at https://docs.docker.com/engine/install/ (on Windows or macOS: Docker Desktop). Check with `docker compose version`.
2. **Unpack Modelarr:**
   ```
   unzip modelarr.zip && cd modelarr
   ```
3. **Look up your user ID:** `id -u` and `id -g`. Put them in `docker-compose.yml` at `user:` (for example `"1000:1000"`), so the app can read your files.
4. **Make the model folder available.** If your models are on the server itself, use that path. If they are on a NAS, mount the share on the host first. Example for SMB in `/etc/fstab`, with a credentials file you create like this:
   ```
   apt-get install -y cifs-utils
   mkdir -p /mnt/3d
   cat > /root/.smbcred <<'EOT'
   username=USERNAME
   password=PASSWORD
   EOT
   chmod 600 /root/.smbcred
   echo '//192.168.1.10/3d /mnt/3d cifs credentials=/root/.smbcred,ro,uid=1000,gid=1000,vers=3.0,iocharset=utf8,nofail,_netdev 0 0' >> /etc/fstab
   systemctl daemon-reload && mount -a && ls /mnt/3d
   ```
   Remove `ro` if Modelarr may rename files or move them to the trash. `uid=1000,gid=1000` must match `user:` in your compose file. Does it not work? See the table of messages in the LXC guide below: the causes are the same.
5. **Choose a backup folder** and create it, preferably on another disk or a NAS share:
   ```
   mkdir -p /mnt/back-ups/modelarr
   ```
6. **Edit `docker-compose.yml`** (remove the `#` where shown):
   ```yaml
   environment:
     - MODELS_DIR=/models
     - BACKUP_DIR=/backups
   volumes:
     - ./config:/config
     - /mnt/3d:/models                    # :ro if the app must not change anything
     - /mnt/back-ups/modelarr:/backups
   ```
7. **Start:**
   ```
   docker compose up -d --build
   docker compose logs -f        # follow along; stop with Ctrl+C
   ```
   Open `http://<ip-of-the-server>:8765`.
8. **Check:** Settings → Media management → **Back up now**, and see whether a `library-….db` is in `/mnt/back-ups/modelarr`.

**Docker Desktop on Windows or macOS:** use paths like `D:/3D:/models` there and remove the `user:` line. On Windows, `start-windows.bat` (see above) is usually simpler and faster.

**Updating:** see "Updating". `update.sh` does not overwrite your own `docker-compose.yml`: on an existing installation, add the backup lines yourself.

### Proxmox LXC (without Docker): step by step

An LXC is a lightweight container with its own Debian or Ubuntu. This guide is written for the template `debian-13-standard_13.6-1_amd64.tar.zst`; with Ubuntu the steps are the same. You run all commands as `root` in the console of the container.

**1. Create the container** (Proxmox → top right **Create CT**)

| Tab | Setting |
|---|---|
| General | Hostname `modelarr`, a root password. **Turn "Unprivileged container" off**; that lets you mount the NAS share later. |
| Template | `debian-13-standard_13.6-1_amd64.tar.zst` (or an Ubuntu template) |
| Disks | 10 GB or more. The database and thumbnails live here too (tens of thousands of thumbnails take a few GB). |
| CPU | 2 cores |
| Memory | **4096 MB**, swap 512 MB. With 2048 MB, memory fills up during the first scan of tens of thousands of models and the container starts swapping (slow, lots of disk activity). |
| Network | Bridge `vmbr0`, IPv4 via DHCP (give it a fixed address in your router) or a static IP |
| Confirm | Tick "Start after created" |

Did you already create the container with less memory? Increase it afterwards: container → **Resources → Memory → Edit**. That takes effect immediately; you do not have to reinstall anything.

**2. Allow SMB/CIFS.** Go to the container → **Options → Features → Edit**, tick **SMB/CIFS** and restart the container.

**3. Update and install tools** (console of the container, log in as `root`):

```
apt-get update && apt-get -y upgrade
apt-get install -y unzip cifs-utils
```

**4. Mount the NAS share.** First create a credentials file. Use an editor as below and not `printf`: a password containing `%` or `\` goes wrong that way. Watch the username: a typo gives "Permission denied".

```
mkdir -p /mnt/3d-modellen
cat > /root/.smbcred <<'EOT'
username=YOURUSERNAME
password=YOURPASSWORD
EOT
chmod 600 /root/.smbcred
echo '//192.168.1.10/3d /mnt/3d-modellen cifs credentials=/root/.smbcred,ro,vers=3.0,iocharset=utf8,nofail,_netdev 0 0' >> /etc/fstab
systemctl daemon-reload
mount -a
ls /mnt/3d-modellen
```

The last command must show your folders. `ro` means read-only. If you want Modelarr to be allowed to rename files or move them to the trash, use `rw` and give the account write permission on the Synology.

Is there already a line for this share in `/etc/fstab` and do you want to change an option? Remove the old line (`nano /etc/fstab`), run `umount /mnt/3d-modellen` and then `mount -a`. `mount -o remount` does not work for CIFS options.

**5. Get the zip file into the container.** The easiest way is via the share: put `modelarr.zip` from your PC in a new folder `_install` on the share, and unpack it:

```
mkdir -p /root/inst && cd /root/inst
unzip /mnt/3d-modellen/_install/modelarr.zip
cd modelarr
```

Afterwards, remove the folder `_install` from the share again. Prefer no share? Turn on SSH in the container (`apt-get install -y openssh-server`, set `PermitRootLogin yes` in `/etc/ssh/sshd_config` and run `systemctl restart ssh`) and copy from your PC with `scp modelarr.zip root@<ip>:/root/`. Turn root login with a password off again afterwards.

**6. Install:**

```
sh install-lxc.sh
```

The script installs Python and the components, puts the program in `/opt/modelarr`, keeps your data in `/var/lib/modelarr` and creates a service that starts at boot. It takes a few minutes. The folder `/mnt/3d-modellen` from step 4 is the default `MODELS_DIR`. Check with:

```
systemctl status modelarr
hostname -I
```

**7. Open it.** Go to `http://<ip-of-the-container>:8765`. The first scan starts by itself. Follow the progress in the app, or in the console with `journalctl -u modelarr -f`.

**8. Set a backup folder.** Choose a place on another machine than the container, for example a second share on the NAS. On the NAS, create a shared folder `Backups` (with write permission for the same account) and mount it in the container:

```
mkdir -p /mnt/back-ups
echo '//192.168.1.10/Backups /mnt/back-ups cifs credentials=/root/.smbcred,rw,vers=3.0,iocharset=utf8,nofail,_netdev 0 0' >> /etc/fstab
systemctl daemon-reload
mount -a
mkdir -p /mnt/back-ups/modelarr
```

Then put the folder in `/etc/modelarr.env` (open with `nano /etc/modelarr.env`):

```
BACKUP_DIR=/mnt/back-ups/modelarr
```

Run `systemctl restart modelarr`. You can also set the folder in the app (Settings → Media management → **Backup folder**); that setting takes precedence. Click **Back up now** and check whether a `library-….db` is in `Backups/modelarr` on the NAS.

Deliberately create the folder `/mnt/back-ups/modelarr` yourself, **while the share is mounted**. Modelarr does not create a missing backup folder itself. If the share is not mounted at startup (NAS still off), the folder does not exist, the backup fails with a clear message and a new attempt follows after an hour. That way your backups never silently end up on the container's own disk.

**9. Start at boot.** In Proxmox, set **Options → Start at boot** for the container to **Yes**. Also make a Proxmox backup of the container (Datacenter → Backup) if you want to be able to restore the whole installation.

**Updating:** put the new zip in the container (for example in `/root`) and run:

```
cd /opt/modelarr
sh update.sh --upgrade /root/modelarr.zip
```

The database and thumbnails are kept. Your existing `/etc/modelarr.env` is not overwritten: add `BACKUP_DIR` there yourself.

**Messages when mounting the share**

| Message | Cause and solution |
|---|---|
| `mount error(13): Permission denied` | The NAS refuses the login. Check with `cat -A /root/.smbcred` that there is no typo, space or odd character in it. As a test, type the password by hand: `mount -t cifs //192.168.1.10/3d /mnt/3d-modellen -o username=USERNAME,vers=3.0`. If that works, the mistake is in the credentials file. Otherwise: check that the account may use SMB on the Synology and has permissions on the share, and try `vers=3.1.1` or `vers=2.1`. |
| `mount error(22): Invalid argument` | Usually a duplicate or incorrect line in `/etc/fstab`, or `mount -o remount` on a CIFS mount. Remove the old line, `umount` and `mount -a`. |
| `Operation not permitted` | The SMB/CIFS feature is not turned on (step 2), or the container is unprivileged. |
| `mount: ... could not resolve address` | Check the IP address or name of the NAS and whether the container has network (`ping 192.168.1.10`). |
| The share is empty after a restart | The NAS was not on yet when the container started. Run `mount -a` and `systemctl restart modelarr`. |

## Configuration
| Variable | Default | Meaning |
|---|---|---|
| `MODELS_DIR` | – | Default root folder(s), comma-separated |
| `CONFIG_DIR` | `/config` (Docker) | Database, thumbnails and settings |
| `PORT` / `HOST` | `8765` / `0.0.0.0` | Port and bind address |
| `AUTH_USER` / `AUTH_PASS` | – | Creates an administrator account at first start (if there are no accounts yet) |
| `MAX_FILE_MB` | `400` | Larger files do not get a thumbnail |
| `YIELD_TO_USERS` | `1` | `0` = the background task never pauses when you use the app |
| `BACKUP_DIR` | `<config>/backups` | Folder for the daily backups (see "Backups"); the setting in the app takes precedence |
| `ALLOW_ORGANIZE` | – | `1` = allow renaming/moving for the roots from `MODELS_DIR` (by default index only) |

Other settings (scan interval, extensions, thumbnail size, extra root folders, authentication,
API key) are in the app under **Settings**.

## Bambuddy integration
If you use [Bambuddy](https://github.com/maziggy/bambuddy) (self-hosted print management for Bambu Lab printers) you can connect it in two ways. It is optional and stays off while the address or key is empty.
1. In Bambuddy, create a key under **Settings → API Keys** (it is shown only once).
2. In Modelarr, enter the address (for example `http://192.168.1.20:8000`) and the key under **Settings → General → Bambuddy**. Click **Save** and then **Test connection**.
- **Sending a model:** open a `.3mf`, `.gcode` or `.stl` model and click **↗ Send to Bambuddy…**. Choose **Put in library**, or pick a printer and choose **Add to queue**. Nothing is ever started: you start it yourself in Bambuddy. Only administrators see this button. **Bambuddy's queue only accepts sliced files** (`.gcode` or a 3MF with G-code inside, i.e. exported as "sliced" from your slicer). An STL or an unsliced 3MF can be put in the library but not in the queue; Modelarr tells you this beforehand.
- **Colors in the printers:** in the "To Bambuddy…" window, after choosing a printer, you see which spools are really in it now (AMS and external spool), with color name and material. This comes from the printer's status in Bambuddy and also works for spools without RFID; the remaining weight is only known for Bambu RFID spools. The list is also in the API: `GET /api/bambuddy/colors` (optionally `?printer=ID`). The API key in Bambuddy needs the **Read Status** permission for this.
- **Print history:** every 30 minutes (or with **Sync now**) Bambuddy's print log is imported into Modelarr's print log. An entry is linked to the model with the same name, only if that is unambiguous (with two models of the same name the `.3mf` is chosen; if more remain it is skipped). Successful and failed prints are imported, with printer, weight, time and the reason if any. Prints that are still running or were cancelled, and entries without a matching model, are not imported; they are tried again next time. An entry is imported only once, even if you delete it in Modelarr later.
- **Filament use and Spoolman:** Bambuddy tracks filament use itself. If you import prints through the sync, do **not** also let Modelarr deduct use from a spool, or it is deducted twice.
- **Key:** the API key is stored in Modelarr's database (like its own API key) and is never sent back to the browser. **Clear key** turns the integration off.

## How new files are picked up
- Live file watcher (inotify) on every root folder on a local disk, with a 3 second debounce. On network shares (NFS/SMB/CIFS)
  the watcher is not used: it gets no events for changes from other computers anyway, and setting it up over a large share
  took minutes before the website became available.
- An extra scan every N minutes (default 5): this is how NFS/SMB shares are kept up to date, because they do not pass on events
  for changes made from other computers.
- New or changed files are only picked up once they are 10 seconds old *and* their size has stayed the same for 10 seconds
  (copies over SMB/NFS often keep the old date). A first import therefore takes at least about 10 seconds longer.
- Symlinks are not followed.
- Moved/renamed outside the app (same size + date) = same model, categories are kept.
- If a root folder is empty or offline, nothing is removed from the library.
- Folders that start with `.`, `@` or `#` (e.g. Synology `@eaDir`, `#recycle`) are skipped.
- Check startup time: `journalctl -u modelarr | grep -E "Database gereed|Webserver start|Bestandswachter"` (Docker: `docker logs modelarr`).

## Search and filters
The search field searches file name, display name, category, extension, folder and 3MF info (designer, title, printer...).
Multiple words must all match. Limit to one field with a prefix: `naam:` (name) `ext:` `cat:` `map:` (folder) `ontwerper:` (designer) `kleuren:` (number of colors, e.g. `kleuren:3`),
for example `rack ext:3mf cat:server map:lab` or `cat:"10 inch"`.
There are also filters on category, format and: no preview, recently added (default 7 days) and large files
(default from 50 MB); both thresholds are under Settings → Media management.

## Duplicates
Under **Duplicates** you find files that are in your library more than once:
- **Identical:** exactly the same content (hash), also under a different name or in a different folder. Only files of the same size
  are compared, so little is read. When a new duplicate file appears, there is a message in Activity → History.
- **Possibly the same mesh:** same number of triangles and dimensions (e.g. STL and 3MF of the same model). That is a hint, not proof.
With "Move to trash" you move a file to `<root folder>/.prullenbak` (the trash folder); nothing is deleted for good and the last copy
of a group can never be moved. In the library there is a "Duplicate files" filter and a ⧉ label on the cards.

### Models from the library to the trash

Select models in the library (checkboxes, Shift+click for a range, or "Select all") and choose **🗑 Move to trash**. You first get a confirmation with the number. The files go to `<root folder>/.prullenbak` and are not deleted for good. To get them back, move them out of that folder and start a scan. This only works for roots where "move" is turned on (Settings → Media management); models inside a zip are skipped. What fails stays selected, with the reason in the message. The log (Activity → History) records every moved file. The buttons "Add to category" and "Remove from category" next to it do not touch the files themselves.

**Right-click menu:** right-click a model (card or table row) for the same actions: add to category, remove from category, favorite, not favorite and move to trash. If the model is in your selection, the menu applies to the whole selection, otherwise only to that model. After every action the selection is cleared. Only what failed when moving to the trash stays selected. Guests get the normal browser menu. On a phone or tablet you get the same menu by pressing and holding a model for about half a second; tap "Add to category" or "Remove from category" to see the categories.

## Filing lots of models: folders, rules and fast selecting

**Settings → Auto-organize** (also reachable via a link on the Categories page):

- **Categories from folders.** Every top-level folder of your root folders can become a category. You see per folder the number of models and whether they are already filed. Tick the folders you want (or choose "Select all" / "Only those not filed yet"), change the category name if needed (an existing category is fine too) and choose **Apply**. All models in that folder, including in subfolders, go in the category. This never removes anything and can safely be repeated. Models that are directly in a root folder have no folder and do not take part. This remembers the folder: a rule "folder is …" is added, so **new files in that folder (including subfolders) get the same category at the next scan**. Folders you had already filed with an earlier version (with a category named like the folder) get that rule automatically on update; with a different category name, file the folder once more. If you delete the rule under Rules, automatic filing stops for that folder.
- **Rules.** "Path contains", "name contains" or "extension is" a text, then the model belongs in a category. New files get the category automatically during the scan. With **Apply all rules to existing models now** the existing models are included too. For every rule you see how many models match and how many are not yet filed. The path counts from the root folder with / between folders, for example `10 inch rack/`. A rule never removes a category.

**Selecting faster in the library** (for administrators):

- As soon as something is selected, a click on a card or row selects (not only a click on the checkbox). **Double-click** opens the model.
- **Ctrl/Cmd+click** starts a selection, **Shift+click** selects everything between two models.
- **Drag a rectangle** over the models to select them. With Ctrl, Cmd or Shift added, you add to the existing selection. At the top or bottom edge the list scrolls along by itself.
- **Ctrl/Cmd+A** selects everything that fits the current filter (also on other pages). **Escape** or a click next to the models clears the selection.

## Safe by default
By default the app only indexes: renaming files or moving them to the trash must be turned on per root folder
(Settings → Media management, or `ALLOW_ORGANIZE=1`). The display name, notes and so on in the database can always be changed.
If you also mount your volume `:ro`, the app can do nothing at all to your files.
If the config folder (with the SQLite database) is on a network share (NFS/SMB), the app warns you: SQLite is unreliable there.

## Notes, favorites, source and print status
Per model: favorite (★), source link, notes and print status (unknown / to print / printed). Everything is searchable
(`notitie:` and `bron:`, i.e. notes and source) and filterable; for several models at once, use the selection in the library.

## Thumbnails
- **3MF, FCStd and G-code:** the embedded image of the file is used if there is one (e.g. the plate image from Bambu Studio);
  otherwise the app renders it itself. In Settings you can always make it render itself.
- **Own capture:** rotate a model in the detail window and choose "View as thumbnail". That stays until you choose "Regenerate thumbnail"
  or the file changes.
- **Gentle on a NAS:** the background task runs at low priority, pauses when you use the app, can insert a pause between
  thumbnails and can be paused under Activity → Queue.

## More file types
Besides the model formats with preview, CAD and project files are indexed by default too (STEP, F3D, Blender, SketchUp, SolidWorks,
FBX, DXF...). They appear in the library without a 3D preview, are searchable and take part in the duplicate check.
Zip, rar and 7z are not on by default: add them under Settings → Media management → File extensions if you want to catalog packages as a whole.

## 3MF information
From 3MF files the title, designer, application, license and creation date are read, plus (when present) printer, layer height,
nozzle, filament type and, for Bambu Studio, print time and filament use. Visible in the detail window and searchable.

**Colors:** for a sliced Bambu/Orca project the app counts the filaments that are really used (with consumption). For a project that is not sliced yet it counts the filaments that objects are assigned to; colors that are only painted onto parts of an object do not count then. You see the color swatches and the number in the detail window, search with `kleuren:3` and filter with **Multicolor (2+ colors)**. On the first start after updating, all 3MF files are read once more (in the background); a 3MF without color information shows nothing.

## Printers and "does this fit my printer?"
Under Settings → Printers you enter your printers with the bed size (X, Y, Z in mm); there are presets for Bambu Lab
(A1 mini, A1, P1P, P1S, X1 Carbon, P2S, H2S; always check the sizes against your own printer, the H2D is missing because sources differ).
Every model then shows "Fits on: ✓ P1S · ✗ A1 mini" and in the library there is a "Fits on …" filter. A model may be rotated 90°;
the check uses the dimensions of the whole model, so for a 3MF with several parts, those of the whole layout.

## Zip files
Models in zip files are searched and previewed without unpacking (only that one part is temporarily extracted). They appear in the
library with the label ZIP, with thumbnail, dimensions, categories, notes and take part in the duplicate check (also against loose copies).
A zip that you move or rename keeps its models; if the zip changes, existing parts keep their categories.
Limitations: only `.zip` (no rar/7z), parts larger than `MAX_FILE_MB` are skipped, and a part from a zip cannot be
renamed or moved to the trash (you can change the display name). You can turn it off under Media management; those models then disappear from the library.

## Multiple plates (Bambu Studio / OrcaSlicer)
If a 3MF has multiple plates, the viewer shows tabs "All / Plate 1 / Plate 2 …" and you can keep the print log per plate.
PrusaSlicer files have no plates.

## Print log and Spoolman
Per model you log prints (succeeded or failed, printer, plate, weight, note). A successful print sets the model to "printed"; the library has
the filter "Previously failed". If you have Spoolman, enter its address under Settings → General (in Docker: the container name or the NAS address, e.g.
`http://spoolman:7912`). When logging you choose a spool and the usage (grams) is deducted in Spoolman. That happens first: if it fails,
nothing is logged. Deleting a log line does not reverse the usage in Spoolman.

## Opening in your slicer
- **Open in Bambu Studio** (or OrcaSlicer / PrusaSlicer, selectable under General): the app makes a temporary, signed download link (10 minutes, with no
  password in the link) and passes it to the slicer, which fetches the file itself. The address of the app must therefore be reachable from your computer.
  Whether Bambu Studio accepts such an address on your local network cannot be tested without the slicer; if it does not work, use Download or the next option.
- **Open with default application**: only appears if your browser runs on the same computer as the app (e.g. the Windows version); the file then
  opens with the program Windows/macOS chooses for it.

## Formats
Thumbnails and 3D view: STL, 3MF (including slicer files and multiple plates), OBJ, PLY, GLB/GLTF.
OBJ/GLB/GLTF are read as Y-up, STL/3MF/PLY as Z-up.

## Moving between Windows, Docker and Synology
The app only knows a folder under the path as it sees it itself: `\\192.168.1.5\3d` on Windows, but `/models` in Docker (to which you yourself link `/volume1/3d` via `/volume1/3d:/models`).
The Synology path `/volume1/3d` therefore never appears in the app. All paths in the database are therefore different per platform; the rest (thumbnails as ordinary PNG files, categories, notes, print log, accounts) is the same everywhere.
- **Simplest:** run one instance (for example Docker on the NAS) and use the browser on your Windows PC. Then there is one database and you do not have to move anything. "Open in Bambu Studio" works from your PC too.
- **Moving an existing library** (for example from Windows to Docker): stop both, copy `library.db` and the `thumbs` folder from the `config` folder to the `config` volume of the new place and start the app.
  The old root then shows as "not reachable" (nothing is removed). Under Settings → Media management, choose **Change path** for that root and enter the path as the new place sees it (for example `/models/10 inch rack`).
  The app shows how many files it finds there and asks for confirmation. All models keep their categories, notes, favorites, print log and thumbnails, including the own captures. Slashes are converted automatically (`\` to `/` and back).
- **Has the new place already scanned the folder** (for example via `MODELS_DIR`)? Then the same files are in there twice. Give the old root the same path under **Change path**: the app merges them and the models with your data replace the fresh duplicate entries.
- **Modification times:** Windows (SMB) and Linux sometimes round the modification time of a file slightly differently. The app therefore lets differences of up to 2 seconds pass and does not regenerate thumbnails.
- **Do not:** run two instances on the same database, or put the database on a network share. Keep the database local to the app. If Spoolman is on `localhost`, change the address under Settings → General.

## Users and access
Without accounts, anyone with access to the address can do everything (the app warns about that). First create your own
**administrator account** under Settings → Users; from that moment on everyone has to log in. After that you can add **guests**, for example acquaintances who may use your collection:
- **Administrator:** everything.
- **Guest (viewer):** view, search and filter the library, and (set per guest) download models and open them in the slicer. A guest cannot change
  or manage anything, and does not see notes, print log, favorites or the file paths on your disk. Without download permission a guest only sees the thumbnails.
  Guest downloads appear with their name in Activity → History.
- **Uploading:** set per guest (column "Upload"; administrators always can). Anyone allowed to upload sees the **⬆ Upload** button in the library: choose the root folder and folder (or create a new folder), tick the categories and pick one or more models. A file with an existing name is never overwritten ((2) is added), only allowed file types and files up to `MAX_FILE_MB` are accepted, and nothing is ever written outside the root folder. The root folder must be writable (not mounted `:ro`). The model appears after the next scan (a few seconds) with the chosen categories; uploads show up in Activity → History. A guest with upload permission still cannot change anything else and does not see paths on your disk.
- **Email address (optional):** you can store an email address with an account; logging in then also works with that address. The app does not send email itself (no mail server is configured).
- **Security:** passwords are stored encrypted (at least 8 characters), after 5 failed attempts logging in is blocked for 10 minutes (per address), the session cookie
  cannot be read by scripts and requests from other websites are refused. If you change a password or disable an account, the running session expires immediately.
  You cannot delete or demote the last administrator; "Delete all accounts" turns logging in off again.
- **Sharing on the internet:** only do that via HTTPS (for example your NAS's reverse proxy), because without HTTPS passwords travel unencrypted.
  Behind a reverse proxy all users show the same address, so the block after failed attempts then applies to everyone together.
- **Existing login:** a previously configured single login automatically becomes an administrator account on update. `AUTH_USER`/`AUTH_PASS` create an administrator at first start
  if there are no accounts yet. The API key (header `X-Api-Key`) grants administrator rights for integrations; signed download links keep working for 10 minutes without logging in.

## API and integrations (API key)

The API key is under **Settings → General** (that is also where you create a new one; the old one then stops working). Send it as the header `X-Api-Key`. With it you reach the API without logging in, with **administrator rights**. So treat it like a password:

- Never put it in a link (`?apikey=` is deliberately refused) and do not share it.
- For requests with the key you do not need to send an `X-Requested-With` header.
- Only use it on your own network or via https.

All responses are JSON. Error messages have the form `{"error": "…"}`. In the examples `nas:8765` is the address of Modelarr and `KEY` is your API key.

**Reading**

| Command | What it does |
|---|---|
| `GET /api/rev` | Short status: number of thumbnails in the queue (`pending`), failed (`failed`), groups of duplicates (`dups`) and the progress of a running scan (`scan`). Handy for Home Assistant. |
| `GET /api/status` | Counts, root folders and health messages. |
| `GET /api/library?page=0&size=50` | Models, per page. Without `page` you get the whole list (a large response with tens of thousands of models). |
| `GET /api/history` | The last 300 events (the log). |
| `GET /api/wanted` | Models whose thumbnail failed, with the reason. |
| `GET /api/duplicates` | Groups of duplicate files. |
| `GET /api/file/<id>` | Download the model file itself. |
| `GET /api/thumb/<id>.png` | The thumbnail. |

With `/api/library` you can use the same search and filter rules as in the app: `q` (search text with prefixes such as `ext:3mf cat:server map:lab`), `cat` (category id, `none` or `all`), `ext`, `flt` (`all`, `nopreview`, `recent`, `big`, `dup`, `fav`, `toprint`, `printed`, `failedprint` or `fit:<printer-id>`), `sort` (`name`, `added`, `size`), `page` (starts at 0) and `size` (number per page, `0` = all). The response contains `models` (the page), `total` (the number that match), `all` (the number in the library), `pages` and `ids` (all ids that match).

**Changing** (POST, with `Content-Type: application/json`)

| Command | Body |
|---|---|
| `POST /api/models/<id>` | One or more of: `display` (display name), `notes`, `favorite` (true/false), `printed` (`""`, `"toprint"`, `"printed"`), `source_url`, `filename` (only if renaming is on for that root). |
| `POST /api/models/bulk` | `{"model_ids": [1,2,3], "favorite": true}` and/or `"printed": "toprint"`. |
| `POST /api/categories` | `{"name": "Rack"}`, returns the `id`. |
| `POST /api/assign` | `{"model_ids": [1,2,3], "category_id": 4, "action": "add"}` (or `"remove"`). |
| `POST /api/models/trash` | `{"ids": [5,6]}`: moves duplicate files to `.prullenbak` (never the last copy). |
| `POST /api/tasks/scan/run` | Start a scan. Other tasks: `rebuild` (all thumbnails again), `backup`, `thumbcheck`. |
| `POST /api/wanted/retry` | `{}` retries all failed thumbnails, or `{"ids": [..]}`. |

**Examples**

```
# first 50 favorite models with "rack" in the name
curl -H "X-Api-Key: KEY" "http://nas:8765/api/library?page=0&size=50&q=rack&flt=fav"

# mark model 12 as a favorite and add a note
curl -X POST -H "X-Api-Key: KEY" -H "Content-Type: application/json" \
     -d '{"favorite": true, "notes": "Print in PETG"}' http://nas:8765/api/models/12

# add category 3 to a number of models
curl -X POST -H "X-Api-Key: KEY" -H "Content-Type: application/json" \
     -d '{"model_ids": [12, 13, 14], "category_id": 3, "action": "add"}' http://nas:8765/api/assign

# start a scan and follow the progress
curl -X POST -H "X-Api-Key: KEY" http://nas:8765/api/tasks/scan/run
curl -H "X-Api-Key: KEY" http://nas:8765/api/rev
```

Python:

```python
import requests
api = "http://nas:8765"; h = {"X-Api-Key": "KEY"}
st = requests.get(f"{api}/api/rev", headers=h).json()
print(st["pending"], "thumbnails in the queue")
```

Home Assistant (`configuration.yaml`):

```yaml
sensor:
  - platform: rest
    name: Modelarr thumbnails to do
    resource: http://nas:8765/api/rev
    headers: {X-Api-Key: KEY}
    value_template: "{{ value_json.pending }}"
    scan_interval: 60
```

What is not listed here (roots, printers, users, settings) is possible too, but is meant for the app itself and may change from version to version. If you want to use it, look in `app.py` at the `@app.get` and `@app.post` lines.

## Backups
Every day Modelarr makes a copy of `library.db`. You decide **where** it goes, and the backups always go to that folder.

**Setting the folder** (choose one of the two):
- In the app: Settings → Media management → **Backup folder**. Type a full path as the app sees it (`/backups`, `/mnt/back-ups/modelarr` or `D:\Backups\Modelarr`), or choose a folder with **Choose…**. The app checks that it can write in the folder and immediately makes a first backup, so you see straight away that it works.
- With the environment variable `BACKUP_DIR` (in `docker-compose.yml`, `/etc/modelarr.env` or `start-windows.bat`). That is the default; the setting in the app takes precedence. If you empty the field in the app, `BACKUP_DIR` applies again.
- With neither: the folder `backups` in your config folder.

Preferably choose a folder **outside** the config folder, on another disk or on the NAS: a backup that is on the same disk as the original disappears together with that disk. In Docker the path is a path inside the container: link the folder as a volume (`/mnt/back-ups/modelarr:/backups`) and use `/backups`.

**Behavior:**
- Always in the chosen folder. If it is not reachable (for example a NAS that is off or a share that is not mounted), the backup fails with a message in Settings → Media management and under System → Tasks, and a new attempt follows after an hour. The app **never silently writes to another folder**.
- A missing folder is not created by the scheduled backup, so no empty folder appears on the wrong disk. Create the folder yourself, while the share is mounted. Only if you enter the folder in the app is it created if needed. The default folder `config/backups` creates itself.
- If the backup folder is inside a root folder, start the folder name with a dot (for example `/mnt/3d-modellen/.back-ups`): such folders are not scanned. The folder picker behind **Choose…** does show folders with a dot; you can also just type the path. A new folder is created if the parent path exists and you may write there. If the share is mounted read-only (`ro`) or the account may not write there, you get "not writable".
- A backup is first written as a temporary file and only then renamed. A connection that drops halfway therefore never leaves a half backup behind that can pass for a real one. The database is first copied locally, so SQLite never writes directly on a network share.
- The number of backups kept is set under Settings → Media management (default 7). The oldest in that folder are cleaned up; other files in the folder are left alone.
- Manually with **Back up now** (Settings → Media management) or under System → Tasks.
- Optionally (Settings → Media management) the thumbnails are included as `library-<date>-thumbs.zip`.

The database contains everything the app knows about your models (categories, notes, favorites...), plus the login and API key: treat a backup as sensitive. Your model files and your compose file are not in it.

**Restoring:** stop the app, copy the wanted backup to `library.db` in the config folder and remove `library.db-wal` and `library.db-shm` if they are there. Start the app again.
- Docker: `docker compose stop`, copy to `config/library.db`, `docker compose start`.
- LXC: `systemctl stop modelarr`, `cp /mnt/back-ups/modelarr/library-<date>.db /var/lib/modelarr/library.db`, `rm -f /var/lib/modelarr/library.db-wal /var/lib/modelarr/library.db-shm`, `systemctl start modelarr`.
- Windows: close the app, copy to `config\library.db`, start the app.

Do you want the thumbnails back too? Then unpack the matching zip file in the `thumbs` folder of the config folder. If you do not, that is no problem: at startup (and after every scan) the app checks whether every thumbnail exists and belongs to the right model, and has missing or wrong thumbnails regenerated by itself. Own captures from the viewer only come back if you unpack the thumbnails from the backup.

Also put the backup folder in a backup outside the house (for example Hyper Backup on a Synology): a backup in the same location as the original does not help with fire or theft.

## Language (Dutch / English)
At the bottom left of the navigation (and on the login page) are the NL and EN buttons. The choice is remembered per browser; without a choice the app follows the language of the browser.
- Dutch is the source language. The English text is in `static/i18n-en.js` (Dutch text, English text) and is applied in the browser on the page, also to messages from the server. Names of models, categories and notes are never translated.
- The Logs page stays Dutch. A text that is not in the word list stays Dutch.
- **Adding a text:** put it in `static/i18n-en.js` under `exact` (whole text), `phrases` (phrase next to a filled-in value) or `patterns` (regular expression for a different word order). `node tests/i18n_test.mjs` and `python tests/test_i18n_server.py` report which visible text does not have a translation yet.

## Tests
All in one go: `python tests/run_all.py` (requires node and the packages from requirements.txt; takes a few minutes). Separate parts:
- `python tests/<name>.py` for the Python tests (database, scanner, accounts, moving paths, print log, zip and plates, backup).
- `node tests/ui_test.mjs` runs the real `static/app.js` with a simulated page and server and runs the checks in `tests/ui/` (optional: `node tests/ui_test.mjs <part of the file name>`).
- `node tests/i18n_test.mjs` and `python tests/test_i18n_server.py` for the English version.

## Faster thumbnails (NAS)

Thumbnails are made in the background. On a slow NAS that can take hours to days with tens of thousands of files. Three levers:

- `THUMB_WORKERS=3` (environment variable, default 1): several thumbnails at once. On a DS423 (4 cores, 2 GB RAM) 3 is safe; higher has little point and costs memory.
- `THUMB_MEM_MB=4096` (default 4096, 0 = no limit): memory limit per model. Thumbnails, 3MF info and the 3D viewer run in a separate helper process (`renderproc.py`), so one huge model can no longer fill up the whole server or container. If the limit is exceeded, only that model gets the message "Te weinig geheugen om dit model te verwerken" (not enough memory). With `THUMB_WORKERS=3` you need up to 3 × this limit.
- `THUMB_TIMEOUT=600` (seconds per model, 0 = no limit) and `THUMB_ISOLATE=0` (turn the helper process off; everything then runs inside the app itself, for debugging only).
- `THUMB_MAX_TRIS=250000` (default): models with more triangles are thinned out for the thumbnail. A thumbnail is 384 px, so the difference is not visible, but a model of 1 million triangles is well over 4x faster this way.
- Let the PC do the heavy work: run Modelarr locally on the whole share, then copy the `config` folder to the NAS and use "Change path" under Media management. The thumbnails stay valid.

## Updating

Put the new zip next to your `docker-compose.yml` (or in your Downloads folder) and run in that folder:

```
sh update.sh                      # finds the newest modelarr*.zip itself
sh update.sh path/to/new.zip      # or give the zip
```

The script replaces the program files, leaves `config/` (database, thumbnails, settings) and your own `docker-compose.yml` alone and rebuilds the container. In an LXC you run it from `/opt/modelarr` (`cd /opt/modelarr && sh update.sh --upgrade /root/modelarr.zip`). On a Synology: SSH or a scheduled task ("User-defined script", as root). Without SSH: unpack the zip via File Station, overwrite everything except `config` and `docker-compose.yml`, and in Container Manager choose Project → Rebuild (the exact name differs per DSM version).

### Large libraries

Searching, filtering, sorting and paging happen on the server: the browser only gets the page you see (for example 100 models) and not the whole list. That keeps memory low and the display fast, even with tens of thousands of models. The list on the server is remembered until something changes.

### Updating the components (Docker and LXC)

`sh update.sh --upgrade` also updates the components besides the program files. The script recognizes by itself where it runs:

- **Docker** (folder with `docker-compose.yml`): rebuilds with `--pull --no-cache`, so with the newest Python base image and the newest packages. Without `--upgrade`, Docker reuses the old layers.
- **LXC** (`/opt/modelarr`, with `venv`): updates the Python packages (`pip install -U`) and restarts the service. Run the script from `/opt/modelarr` there. You update the operating system with `apt-get update && apt-get -y upgrade`. Running `sh install-lxc.sh` again is also fine and safe.

The messages "Running pip as the 'root' user" and "A new release of pip is available" during the build are only notices, not errors. In this version they are turned off.

## License
MIT, see [LICENSE](LICENSE).

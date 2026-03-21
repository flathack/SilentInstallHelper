# SilentInstallHelper

`SilentInstallHelper` ist ein PySide6-Tool fuer stille Installationen mit sichtbarem Fortschritt.
Die eigentliche Ausfuehrung wird komplett ueber JSON-, JSONC- oder YAML-Konfigurationen gesteuert.

## Highlights

- Modi `FULL`, `BASIC` und `SILENT`
- segmentierter, animierter Fortschrittsbalken
- konfigurierbares helles und dunkles Theme
- Live-Status fuer `7z`-Entpacken
- Live-Dateizaehler fuer `icacls`
- eigene Variablen und eingebaute Platzhalter
- PyInstaller-Build fuer Windows

## Start

```powershell
python run.py .\example-config.json
```

## Konfigurationsbeispiele

Im Repo enthalten:

- `example-config.json`
- `config-template.jsonc`
- `config-template-basic.jsonc`
- `config-template-full.jsonc`
- `config-template-silent.jsonc`
- `config-7zip-extract.jsonc`
- `config-example-7z-icacls.jsonc`

## Live-Output

Mit `output_mode` koennen bestimmte Tools besonders gut visualisiert werden:

- `7ZIP`: zeigt Dateinamen und echten 7z-Fortschritt im aktiven Abschnitt
- `ICACLS`: zeigt aktuelle Datei und laufenden Bearbeitungszaehler
- `RAW`: rohe Prozessausgabe

## Build

```powershell
pip install -e .[dev]
.\build.ps1 -Clean
```

Fuer einen Release-Build:

```powershell
.\release.ps1 -Clean
```

## Icon

Das Windows-Icon liegt unter `assets/app.ico`.

## Mehr Details

Die ausfuehrlichere Projektdokumentation steht in [readme.md](./readme.md).

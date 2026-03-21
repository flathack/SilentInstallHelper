# Projektplan: SilentInstallHelper

## 1. Ziel des Projekts

`SilentInstallHelper` soll ein eigenstaendiges Python-Programm werden, das Software-Installationen ueber definierte Kommandozeilen-Schritte ausfuehrt und dem Nutzer waehrenddessen einen klaren Fortschritt anzeigt.

Das Tool soll:

- externe Programme und Installer ueber konfigurierbare Befehle starten
- pro Schritt Statusinformationen fuer den Nutzer anzeigen
- einen Fortschrittsbalken ueber mehrere Installationsschritte darstellen
- unterschiedliche Oberflaechenmodi unterstuetzen: `FULL`, `BASIC`, `SILENT`
- spaeter als Standalone-Anwendung verteilbar sein

## 2. Anforderungen aus der README

### Funktionale Anforderungen

- Das Programm erhaelt als Parameter:
  - Pfad zum Zielprogramm oder Installer
  - Pfad zu einer Konfigurationsdatei
- In der Konfigurationsdatei stehen die Befehle, die nacheinander ausgefuehrt werden.
- Jeder Befehl entspricht einem Schritt im Fortschrittsbalken.
- Jeder Schritt kann eine nutzerfreundliche Beschreibung besitzen, zum Beispiel: `Wir packen Ihre Software aus`.
- Die Konfiguration soll Flags oder Modi unterstuetzen, zum Beispiel `FULL`, `BASIC`, `SILENT`.
- `BASIC`:
  - keine Schliessen- oder Abbrechen-Buttons
- `FULL`:
  - optisch wie ein klassischer Installer mit Weiter-Logik
- `SILENT`:
  - keine sichtbare Oberflaeche

### Nicht-funktionale Anforderungen

- Orientierung an gaengigen Software-Entwicklungsleitfaeden
- schoene, klare Benutzeroberflaeche
- robuste Ausfuehrung auch bei fehlgeschlagenen Schritten
- spaeter einfach paketierbar als Standalone-Python-Anwendung

## 3. Projektumfang

### Im Scope

- Desktop-Anwendung in Python
- Konfigurationsgesteuerte Ausfuehrung von Installationsschritten
- Fortschrittsanzeige und Schritttexte
- UI-Modi `FULL`, `BASIC`, `SILENT`
- Fehlerbehandlung, Logging und Rueckgabecodes
- Beispielkonfiguration und Dokumentation

### Zunaechst nicht im Scope

- Automatische Erkennung aller Installer-Typen
- Remote-Downloads oder Paketverwaltung
- Mehrsprachigkeit ueber Deutsch hinaus
- komplexe Plug-in-Architektur
- Enterprise-Verteilung oder zentrales Management

## 4. Technischer Vorschlag

### Empfohlener Stack

- Sprache: Python 3.12+
- GUI:
  - bevorzugt `PySide6`, weil modern, stabil und fuer Installer-Oberflaechen gut geeignet
- Konfiguration:
  - `YAML` oder `JSON`
  - Empfehlung: `YAML`, weil lesbarer fuer Schrittdefinitionen
- Packaging:
  - `PyInstaller` fuer eine spaetere Standalone-Exe
- Tests:
  - `pytest`

### Grobe Architektur

- `main.py`
  - CLI-Einstiegspunkt, Parameterpruefung, Startmodus
- `config_loader.py`
  - laedt und validiert die Konfigurationsdatei
- `models.py`
  - Datenmodelle fuer Konfiguration, Schritte, Modi
- `executor.py`
  - fuehrt Befehle sequentiell aus, sammelt Ergebnisse
- `ui/`
  - Fenster, Fortschrittsbalken, Statusanzeigen, Buttons
- `logging/`
  - Logdateien und Fehlerprotokoll
- `packaging/`
  - Build-Skripte und Release-Konfiguration

## 5. Vorschlag fuer die Konfigurationsstruktur

Beispielhaft:

```yaml
mode: BASIC
title: SilentInstallHelper
steps:
  - id: extract
    label: "Wir packen Ihre Software aus"
    command: "\"{installer}\" /extract"

  - id: install
    label: "Die Software wird installiert"
    command: "\"{installer}\" /silent"

  - id: cleanup
    label: "Wir raeumen auf"
    command: "cmd /c del /q temp\\*.*"
```

Optional spaeter:

- `timeout`
- `optional`
- `continue_on_error`
- `success_codes`
- `working_directory`

## 6. Arbeitspakete

### Phase 1: Anforderungs- und Konzeptphase

Ziel: Anforderungen praezisieren und technische Richtung festlegen.

Aufgaben:

- README in eine sauber strukturierte Produktspezifikation ueberfuehren
- Zielplattform festlegen, wahrscheinlich Windows
- GUI-Framework final entscheiden
- Format der Konfigurationsdatei festlegen
- Bedienlogik fuer `FULL`, `BASIC`, `SILENT` definieren

Ergebnis:

- technische Kurzspezifikation
- erste Config-Spezifikation
- Architekturentscheidung dokumentiert

### Phase 2: Projektgrundgeruest

Ziel: lauffaehiges Grundprojekt mit sauberer Struktur.

Aufgaben:

- Python-Projekt aufsetzen
- Abhaengigkeiten definieren
- Logging und Fehlerbehandlung vorbereiten
- CLI-Parameter einbauen:
  - Installerpfad
  - Configpfad
- Basismodell fuer Konfiguration und Schritte anlegen

Ergebnis:

- startbares Grundprojekt
- definierte Ordnerstruktur
- erste Validierung der Eingaben

### Phase 3: Konfigurationssystem

Ziel: Konfiguration lesen, pruefen und in interne Modelle ueberfuehren.

Aufgaben:

- YAML- oder JSON-Loader implementieren
- Schema-Validierung einbauen
- Platzhalter wie `{installer}` unterstuetzen
- Fehlertexte fuer ungueltige Konfigurationen sauber ausgeben

Ergebnis:

- stabile Config-Verarbeitung
- Beispielkonfigurationen fuer alle Modi

### Phase 4: Befehlsausfuehrung

Ziel: Installationsschritte verlässlich nacheinander ausfuehren.

Aufgaben:

- Prozessausfuehrung ueber `subprocess`
- Rueckgabecodes auswerten
- Abbruch- und Fehlerlogik definieren
- Logs pro Schritt erzeugen
- Status in Echtzeit an die UI melden

Ergebnis:

- funktionierender Step-Executor
- nachvollziehbares Fehlerverhalten

### Phase 5: Benutzeroberflaeche

Ziel: eine ansprechende und klare Installer-Oberflaeche bereitstellen.

Aufgaben:

- Design fuer `FULL`-Modus erstellen
- reduziertes Fenster fuer `BASIC` bauen
- `SILENT` ohne sichtbares Fenster ausfuehren
- Fortschrittsbalken und Schritttexte anbinden
- visuelle Zustaende fuer:
  - bereit
  - laeuft
  - erfolgreich
  - fehlgeschlagen

Ergebnis:

- nutzbare GUI fuer alle Modi
- sichtbarer Fortschritt waehrend der Installation

### Phase 6: Robustheit und Qualitaet

Ziel: stabiler Betrieb unter realen Bedingungen.

Aufgaben:

- Unit-Tests fuer Config-Parsing und Executor
- Tests fuer Fehlerfaelle
- Test mit realistischen Dummy-Befehlen
- Umgang mit:
  - Dateipfadfehlern
  - fehlenden Rechten
  - Timeouts
  - Installer-Fehlercodes

Ergebnis:

- testbare Kernlogik
- definierte Mindestqualitaet

### Phase 7: Packaging und Auslieferung

Ziel: verteilbare Anwendung fuer Endnutzer.

Aufgaben:

- Build mit `PyInstaller`
- Konfigurations- und Asset-Dateien sauber einbinden
- Start auf Zielsystem testen
- Release-Dokumentation schreiben

Ergebnis:

- erste lauffaehige Standalone-Version

## 7. Meilensteine

- M1: Anforderungen und Technikentscheidung abgeschlossen
- M2: Projektgeruest laeuft mit CLI-Parametern
- M3: Konfiguration wird korrekt geladen und validiert
- M4: Schrittweise Befehlsausfuehrung funktioniert
- M5: GUI fuer `BASIC` und `FULL` ist nutzbar
- M6: `SILENT`-Modus funktioniert ohne sichtbares Fenster
- M7: Standalone-Build ist erfolgreich

## 8. Risiken und offene Punkte

### Risiken

- Installer verhalten sich je nach Hersteller unterschiedlich
- Fortschritt ist technisch oft nur schrittbasiert und nicht prozentgenau
- Manche Silent-Installer liefern schlechte oder uneinheitliche Rueckgabecodes
- UI darf waehrend laufender Prozesse nicht einfrieren

### Offene Punkte

- Nur Windows oder spaeter auch andere Plattformen?
- Soll `FULL` wirklich mehrere Seiten wie ein Wizard haben oder nur installer-aehnlich aussehen?
- Welche Konfigurationssyntax ist gewuenscht: YAML oder JSON?
- Soll ein manueller Abbruch im `FULL`-Modus erlaubt sein?
- Sollen Logdateien fuer Supportfaelle automatisch gespeichert werden?

## 9. Empfohlene Reihenfolge fuer die Umsetzung

1. Spezifikation und Config-Format finalisieren
2. Python-Projekt mit CLI und Config-Loader aufsetzen
3. Executor fuer sequentielle Befehle implementieren
4. `BASIC`-Modus zuerst bauen
5. danach `FULL`-Modus gestalten
6. `SILENT`-Modus ergaenzen
7. Tests, Logging und Packaging abschliessen

## 10. Definition of Done fuer Version 1.0

Version 1.0 ist erreicht, wenn:

- das Tool ueber Parameter gestartet werden kann
- eine Konfigurationsdatei mit mehreren Schritten verarbeitet wird
- jeder Schritt sichtbar oder intern sauber verfolgt wird
- `BASIC`, `FULL` und `SILENT` funktionieren
- Fehler protokolliert und verstaendlich gemeldet werden
- eine Standalone-Version gebaut werden kann
- eine kurze Nutzerdokumentation vorhanden ist

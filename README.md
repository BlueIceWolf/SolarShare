<p align="center"><img src="custom_components/solarshare/brand/logo.png" alt="SolarShare" width="500"></p>

# SolarShare

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BlueIceWolf&repository=SolarShare&category=integration)

**Eine Energieanlage, alle Wohnungen, automatisch berechnete Datenpunkte.**
SolarShare ist eine Home-Assistant-Integration mit einer gemeinsamen Konfiguration
für PV, Netz und optional Batterie. Die Energie wird in gemeinsam beobachteten
Intervallen auf die Wohnungen verteilt. Version **0.2.0** ersetzt die frühere
Einzelzähler-Einrichtung. Es müssen keine separaten Wohnungshelfer erstellt werden.

## HACS installieren / aktualisieren

Home Assistant 2026.10 oder neuer erforderlich.

1. In HACS `https://github.com/BlueIceWolf/SolarShare` als benutzerdefiniertes
   Repository vom Typ **Integration** hinzufügen (oder den Button oben verwenden).
2. SolarShare herunterladen. Bei einer vorhandenen Installation **Erneut herunterladen**
   und `main` auswählen, falls HACS noch keinen neuen Stand anzeigt.
3. Home Assistant vollständig neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → SolarShare**.

Das Repository ist über HACS als benutzerdefiniertes Repository installierbar;
es ist nicht im Standardkatalog gelistet. Icons und Logos für helle/dunkle Ansichten
sind im `brand/`-Ordner enthalten. Einige ältere HACS-Oberflächen zeigen wegen eines
[bekannten Fehlers](https://github.com/hacs/integration/issues/5171) noch einen
Platzhalter; Home Assistant nutzt die lokalen Icons.

## Bestehenden v0.1-Eintrag umstellen

**Den vorhandenen Eintrag nicht löschen.** Nach dem Update bei SolarShare
**Konfigurieren** öffnen. Jetzt die Anlagenquellen auswählen; die bisherige Wohnung
ist bereits vorbelegt. Weitere Wohnungen hinzufügen, dann **Anlage speichern**.
Der frühere Verbrauchsstand bleibt unter seiner bisherigen Sensor-ID als Archiv
erhalten. Er wird nicht nachträglich mit erfundenen PV-/Netzanteilen versehen.
Die neue gemeinsame Berechnung startet mit frischen Messbasen.

Falls mehrere alte Einzelzähler-Einträge existieren: einen zur Anlage umstellen,
die anderen Wohnungen dort hinzufügen und die übrigen alten Einträge deaktivieren.
Ihre Historie bleibt erhalten. Neue Wohnungen werden nur innerhalb der einen
Anlage verwaltet.

## Quellen und Wohnungen einrichten

Einmal für das gesamte Gebäude auswählen:

- kumulative **PV-Erzeugung AC**, **Netzbezug**, **Einspeisung**;
- optional **Batterieladung AC und Batterieentladung AC** als getrenntes Paar;
- bei Batterie die nutzbare Kapazität in kWh;
- maximale plausible Anlagenleistung und erlaubten Zeitversatz der Zählerberichte.

Danach **Wohnung hinzufügen** wiederholen: Name und zugehörigen Verbrauchszähler
auswählen. Unter **Wohnung bearbeiten** lassen sich Name, Zähler, Pause und Zuordnung
später ändern. Erst **Anlage speichern** übernimmt alle Änderungen. Die Wohnungs-ID
und bereits erfassten Werte bleiben beim Bearbeiten erhalten. Einen Zähler zum
Umziehen zuerst in seiner alten Wohnung pausieren.

Quellen müssen Gerätekategorie `energy`, Zustandsklasse `total` oder
`total_increasing` und Einheit Wh/kWh/MWh haben. Keine täglich zurückgesetzten
Zähler, Leistungssensoren oder SolarShare-Ausgabesensoren auswählen. Alle Werte
müssen dieselbe AC-Bilanzgrenze abbilden. Die Integration liest die ausgewählten
Home-Assistant-Entitäten; Hardware muss über ihre jeweilige Integration eingebunden sein.

## Automatisch angelegte Datenpunkte

SolarShare erscheint als **Integration mit einem Anlagengerät und einem Gerät pro
Wohnung**, nicht als Sammlung einzeln anzulegender Helfer.

| Je Wohnung | Zeiträume |
| --- | --- |
| Verbrauch (kWh) | Heute, Monat, Jahr, Gesamt |
| Zugeordnete Solarenergie inkl. bekanntem PV-Speicheranteil (kWh) | Heute, Monat, Jahr, Gesamt |
| Direkter PV-Anteil (kWh) | Heute, Monat, Jahr, Gesamt |
| Netzenergie inkl. bekanntem netzgeladenem Speicheranteil (kWh) | Heute, Monat, Jahr, Gesamt |
| Versorgung aus der Batterie (kWh) | Heute, Monat, Jahr, Gesamt |
| Energie mit ungeklärter Herkunft (kWh) | Heute, Monat, Jahr, Gesamt |
| Autarkie (%) | Heute, Monat, Jahr, Gesamt |
| Quellzählerstand (kWh), mittlere Leistung des letzten Intervalls (W) | Aktueller Messstand / Intervall |

Die Batterieenergie ist eine zusätzliche Aufschlüsselung und darf nicht nochmals
zum Verbrauch addiert werden. Für die Herkunft gilt:
**Verbrauch = Solarenergie + Netzenergie + ungeklärte Energie**.

Am Anlagengerät entstehen PV-Erzeugung, Netzbezug, Einspeisung, Batterieladung und
-entladung (wenn konfiguriert), Gebäudeverbrauch, verbleibender Allgemeinverbrauch
inkl. Messdifferenzen und PV-Eigenverbrauchsquote, jeweils für die vier Zeiträume.
Zusätzlich gibt es Quellzählerstände und einen Datenqualitätssensor.

## Berechnung und Grenzen

Alle 60 Sekunden wird ein gemeinsamer Messrahmen geprüft. Alle Quellen müssen
seit dem vorherigen Rahmen erneut berichtet haben, höchstens fünf Minuten alt sein
und innerhalb des konfigurierten Zeitversatzes liegen (Standard 60 Sekunden).
Auch unveränderte, neu gemeldete Zählerstände zählen über `last_reported` als Bericht.
Die Werte sind eine zeitlich begrenzte **Intervallzuordnung**, keine physische
Messung des Stromursprungs jeder Wohnung.

Ohne Speicher gilt pro Intervall:

```text
Gebäudeverbrauch = PV + Netzbezug - Einspeisung
PV vor Ort = PV - Einspeisung
Solarenergie Wohnung = PV vor Ort × (Wohnungsverbrauch / Gebäudeverbrauch)
Netzenergie Wohnung = Netzbezug × (Wohnungsverbrauch / Gebäudeverbrauch)
Autarkie Wohnung = Solarenergie Wohnung / Wohnungsverbrauch × 100
PV-Eigenverbrauchsquote Anlage = (PV - Einspeisung) / PV × 100
```

Beispiel: 0,4 kWh PV plus 0,6 kWh Netz versorgen 1 kWh Gebäudeverbrauch. Eine Wohnung
mit 0,3 kWh erhält 0,12 kWh PV und 0,18 kWh Netz, also 40 % Autarkie.
Nicht zugeordneter Gebäudeverbrauch bleibt als Allgemeinverbrauch/Messdifferenz
sichtbar und nimmt an derselben proportionalen Verteilung teil.

Mit Speicher wird die AC-Bilanz um Entladung minus Ladung ergänzt. Die deklarierte
Zuordnung priorisiert PV für direkte Lasten, danach Batterieladung. Die virtuelle
Batterie führt PV-, Netz- und unbekannte Herkunft mit proportionaler Entnahme und
angenommenen 95 % Lade-/Entladewirkungsgraden. Diese Herkunft ist modelliert.
Nach Start oder Datenlücke beginnt der Speicherinhalt konservativ als unbekannt;
die Kapazität ist eine obere Anfangsgrenze. Ladung kann diese anfängliche
Unsicherheit verdrängen. Ein späterer SOC-Abgleich ist noch nicht enthalten.

**Bei unbekannter Batterieherkunft wird keine scheinbar exakte Autarkie angezeigt.**
Die kWh unbekannter Herkunft bleiben sichtbar. Bei null Verbrauch ist die Quote
ebenfalls nicht definiert. Gleichzeitig gemessener Bezug/Einspeisung oder
Ladung/Entladung, Batterieexport unklarer Herkunft und unplausible Energiebilanzen
werden nicht automatisch aufgeteilt. Dafür ist feinere Messtechnik bzw. ein
erweitertes Modell nötig.

## Datenlücken, Neustarts und Speicherung

Fehlende, nicht verfügbare, wiederhergestellte, veraltete oder zeitlich unpassende
Quellen führen zu `unavailable`, niemals zu erfundenen Nullen. Ein neuer kompletter
Messrahmen setzt erst eine Basis; nur der folgende vollständige Rahmen liefert
Energie. Fehlende Intervalle werden nicht nachgetragen. Tagesgrenzen starten eine
neue Basis, damit ein Intervall über Mitternacht nicht falsch einem Tag zugeordnet wird.
Tages-/Monats-/Jahreswerte umfassen nur seit Einrichtung beobachtete Daten; sie
importieren keine frühere Recorder-Historie.

Resets oder unplausible Sprünge sperren die Berechnung bis zur Prüfung und
Bestätigung in der Konfiguration. Speicherung erfolgt atomar vor Veröffentlichung.
Bei Schreibfehlern stoppt die Berechnung; bei fehlendem zuvor initialisiertem
Speicher wird kein neuer Nullstand angelegt. Sichern:
`.storage/solarshare.site.<entry_id>` sowie vorhandene alte
`.storage/solarshare.<entry_id>` und die HA-Konfiguration.

Die Integration berechnet keine rechtssicheren Rechnungen. Live-RFID-Ladesitzungen,
Tarife, SOC-Abgleich und ein dauerhaftes Intervall-Auditjournal bleiben separate
Ausbauschritte: [Wallbox-Konzept](docs/WALLBOX.md), [Architektur](docs/ACCOUNTING.md).

## Entwicklung

Die ursprüngliche Dokumentation ist unter [v0.1-Archiv](docs/LEGACY_0_1.md) erhalten.
Rechentests lokal ohne externe Abhängigkeiten:

```sh
python -m unittest discover -s tests -p 'test_*accounting.py' -v
```

GitHub-Prüfungen starten ausschließlich manuell. Die Tests gegen echtes
Home Assistant benötigen Linux und Python >=3.14.2:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests/ha -v
```

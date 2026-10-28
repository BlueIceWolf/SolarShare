<p align="center"><img src="custom_components/solarshare/brand/logo.png" alt="SolarShare" width="500"></p>

# SolarShare

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BlueIceWolf&repository=SolarShare&category=integration)

**Eine Energieanlage, alle Wohnungen, automatisch berechnete Datenpunkte.**
SolarShare ist eine Home-Assistant-Integration mit einer gemeinsamen Konfiguration
für PV, Netz und optional Batterie. Die Energie wird in gemeinsam beobachteten
Intervallen auf die Wohnungen verteilt. Version **0.2.4** ersetzt die frühere
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

## Geführte Einrichtung

Die Einrichtung besteht aus sechs klar getrennten Abschnitten:

1. **Anlage:** Name vergeben.
2. **Wechselrichter:** Den Gesamtertrag des ersten WR zuordnen. Danach erscheint
   eine Liste mit **Weiteren Wechselrichter hinzufügen** und **Alle Wechselrichter
   erfasst – weiter**. Bei drei WR diesen Schritt dreimal durchlaufen. Vorhandene
   WR lassen sich einzeln bearbeiten oder entfernen.
3. **Stromnetz:** Bezugs- und Einspeisezähler am Hausanschluss zuordnen.
4. **Batterie:** Vorhanden ja/nein. Nur bei Ja erscheinen Lade-/Entladezähler und Kapazität.
5. **Wohnungen:** Wohnungen mit ihren Verbrauchszählern hinzufügen oder bearbeiten.
6. **Zusammenfassung:** Alle Zuordnungen prüfen, bei Bedarf zurück zu den
   Einstellungen wechseln und schließlich speichern.

String-Details sind optional und liegen im separaten Einstellungsmenü. Bei
WR-Gesamterträgen bleiben sie leer. Leistungsgrenzen, Zeitversatz und die Bestätigung
einer Prüfsperre stehen unter **Erweiterte Einstellungen**. Bei späterer Konfiguration
öffnet sich direkt die Bereichsauswahl; du musst nicht erneut den ganzen Ablauf durchgehen.

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

## Mehrere Wechselrichter und Stringzähler

Unter **Wechselrichter** lassen sich mehrere Geräte nacheinander hinzufügen. SolarShare
zeigt die Einzelzähler und einen gemeinsamen PV-Gesamtzählerstand an und berechnet
die gesamte PV-Energie aus den einzelnen Zuwächsen. Ein Ausfall oder Reset eines
einzigen Zählers wird nicht hinter den anderen Quellen versteckt. Dafür sind keine
Summenhelfer nötig. Bestehende Zuordnungen mit nur einem PV-Zähler bleiben gültig.

Zusätzlich gibt es **PV-Details / Strings (nur Erfassung)**. Hier können DC-Stringzähler
wie `sensor.growatt_mod_4000_tl_3_total_pv2_solar_energy` separat zugeordnet werden,
während die AC-Ausgangszähler der Wechselrichter die Gebäudebilanz speisen. Die
Detailzähler erhalten eigene Entitäten und fließen nicht nochmals in die PV-Summe,
Autarkie oder Wohnungsverteilung ein. Ein fehlender Detailzähler unterbricht die
AC-Berechnung nicht. Ohne vollständige AC-Quellen bleibt die Verteilung angehalten.

Bei Growatt-Modbus gibt es getrennte Definitionen für `Total PV2 Solar Energy` und
`Total Power Generation`; welcher AC-Gesamtsensor am konkreten Gerät verfügbar ist,
muss anhand der verwendeten Integration und des Modells geprüft werden:
[Growatt-Sensordefinitionen](https://github.com/wills106/homeassistant-solax-modbus/blob/main/custom_components/solax_modbus/plugin_growatt.py).

Jede erzeugte Energiemenge darf nur einmal enthalten sein: entweder den Gesamtwert
eines Wechselrichters auswählen oder dessen vollständige, voneinander getrennte
Teilwerte. **WR-Gesamtwert plus dessen Strings würde doppelt zählen.** Die Integration
kann diese physische Überschneidung anhand unterschiedlicher Entitäts-IDs nicht
automatisch erkennen.

Bei **Messseite der PV-Quellen** AC, DC oder Unklar wählen. AC-Werte am Ausgang
unabhängiger Wechselrichter können direkt für die Gebäudebilanz summiert werden.
DC-Stringenergie liegt vor der Umwandlung; sie darf wegen Verlusten und möglicher
DC-Batterieflüsse nicht unverändert als AC-Erzeugung verrechnet werden. Bei DC oder
Unklar sind Einzel-/Summenstände sichtbar, die Wohnungsverteilung bleibt mit Status
`pv_measurement_boundary_unclear` angehalten. Es wird kein pauschaler Wirkungsgrad
erfunden. AC- und DC-Werte nicht in einer gemeinsamen Summe mischen.

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

Alle 60 Sekunden werden die aktuell verfügbaren kumulativen Zählerstände gemeinsam
abgetastet. Ein unveränderter PV-Zähler nachts oder ein stillstehender Lade-/Bezugs-
zähler ist weiterhin ein gültiger Stand. Für die Differenzberechnung braucht er nicht
alle fünf Minuten einen neuen Änderungsbericht. Fehlende, `unknown`, `unavailable`,
wiederhergestellte oder ungültige Quellen werden niemals durch null ersetzt.

Die Standardberechnung ist eine **Zuordnung anhand verfügbarer Zustandsschnappschüsse**,
keine nachgewiesen zeitsynchrone Messung jeder Quelle. Meldet eine Quellintegration
eingefrorene Zahlen weiterhin als verfügbar, kann dies allein anhand des Zählerstands
nicht sicher von Stillstand unterschieden werden. Unter **Erweiterte Einstellungen**
kann deshalb die **strenge Frischeprüfung** aktiviert werden. Sie verlangt neue
Berichte aller Quellen innerhalb von fünf Minuten und den eingestellten Zeitversatz;
das ist nur für zuverlässig und regelmäßig meldende Integrationen geeignet.
Unabhängig vom Modus unterbricht eine echte Beobachtungspause von über fünf Minuten
die Messbasis. Datenlücken werden nicht nachgetragen.

Der Datenqualitätssensor zeigt verständliche Zustände. Seine Attribute enthalten
`source_diagnostics`, `unavailable_sources` und `sources_without_recent_report`,
damit die betroffenen Entitäten sichtbar sind. Ein alter Änderungsbericht allein
ist im Standardmodus kein Ausfall. Überlappende Growatt-Gesamtzähler desselben WR
(`total_power_generation` plus `total_solar_energy`) werden als Doppelzuordnung
erkannt und dürfen nicht gemeinsam verrechnet werden.

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

Fehlende, nicht verfügbare, wiederhergestellte oder ungültige Quellen führen zu
`unavailable`, niemals zu erfundenen Nullen. In der optionalen strengen Frischeprüfung
gilt dies zusätzlich für veraltete oder zeitlich unpassende Berichte. Ein neuer kompletter
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

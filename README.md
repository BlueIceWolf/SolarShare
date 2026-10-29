<p align="center"><img src="custom_components/solarshare/brand/logo.png" alt="SolarShare" width="500"></p>

# SolarShare

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BlueIceWolf&repository=SolarShare&category=integration)

**Eine Energieanlage, alle Wohnungen, automatisch berechnete Datenpunkte.**
SolarShare ist eine Home-Assistant-Integration mit einer gemeinsamen Konfiguration
für PV, Netz und optional Batterie. Die Energie wird in gemeinsam beobachteten
Intervallen auf die Wohnungen verteilt. Version **0.3.0** baut auf der gemeinsamen Anlage auf und erweitert sie um Wallboxen, Tarife und getrennte Messwerterfassung; Version 0.2.6 ersetzt die frühere
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
wiederhergestellte oder ungültige Quellzählerstände werden nicht erfunden. Die
ausdrückliche PV-Nachtannahme für Ertragszuwächse ist unten getrennt beschrieben.

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

## Nächtlicher Neustart und schlafende PV-Wechselrichter

Seit 0.2.6 ist unter **Erweiterte Einstellungen** der PV-Nachtmodus standardmäßig
aktiv. Wenn `sun.sun` einen gültigen, nicht wiederhergestellten Zustand
`below_horizon` meldet, können fehlende, unbekannte oder nicht verfügbare PV-Zähler
als schlafende Wechselrichter behandelt werden. Dann wird **für den Energiezuwachs
dieser PV-Quellen null angenommen**. Das funktioniert auch nach einem HA-Neustart,
wenn diese WR noch überhaupt keinen Zahlenwert geliefert haben.

Dies ist eine ausgewiesene Nachtannahme, kein gemessener PV-Zählerstand. Die realen
Quellzähler bleiben nicht verfügbar, wenn sie nichts liefern. Letzte gültige Stände
werden nur für die Diagnose gespeichert. Der Datenqualitätssensor zeigt den
PV-Nachtbetrieb und `pv_night_assumed_zero`; `last_known_pv_counters_kwh` enthält
gegebenenfalls die früheren echten Stände. Beim Wechsel zwischen echten Zählern und
Nachtannahme startet eine neue Messbasis. Ein morgens wieder auftauchender hoher
Gesamtzählerstand wird somit nicht als frische Erzeugung verrechnet.

Ein tatsächlich verfügbarer PV-Zähler wird auch nachts normal ausgewertet, selbst
wenn er Zuwächse meldet. Tagsüber oder bei unbekanntem Sonnenstand gibt es keine
Nullannahme. Die HA-Standort-/Sonnenkonfiguration muss stimmen. Wer diese Annahme
nicht verwenden möchte, kann den Nachtmodus ausschalten.

**Netzbezug, Einspeisung, Batterie und Wohnungszähler müssen weiterhin reale gültige
Stände liefern.** Schläft auch deren Messquelle und meldet unbekannte Werte, kann
die vollständige Verteilung weiterhin nicht erfolgen. Dafür ist eine unabhängig
verfügbare Messquelle nötig. Die Nachtannahme darf nur für reine PV-Erzeugungsquellen
verwendet werden, nicht für einen AC-Gesamtzähler, der nachts Batteriestrom mitzählt.

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
SOC-Abgleich und ein dauerhaftes Intervall-Auditjournal bleiben separate
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

## Diagnose: Benötigter Zähler nicht verfügbar

Beim Datenqualitätssensor unter **Details → Attribute** zeigen `unavailable_sources`
und `source_diagnostics` die betroffenen Originalentitäten und deren Originalzustand.
`unknown`, `unavailable`, fehlende oder nur wiederhergestellte Entitäten sind keine
gültigen Zahlen. Das ist etwas anderes als ein verfügbarer PV-Zähler, dessen kWh-Stand
nachts einfach stehen bleibt. Netz-/Batteriesensoren müssen ebenfalls gültige Werte
liefern; ihr Energiefluss wird bei einem Ausfall nicht als null angenommen.

Wenn ein Wechselrichter nachts die Kommunikation abschaltet und auch die Netzwerte
nicht mehr liefert, kann SolarShare ohne eine unabhängig verfügbare Messquelle keine
vollständige Gebäudebilanz berechnen. Prüfe die Quellintegration bzw. die ausgewählten
Zähler. Einstellungen allein können fehlende Messwerte nicht rekonstruieren.

Für ausschließlich schlafende PV-Quellen gilt die oben beschriebene explizite Nachtannahme; fehlende Netz-/Batteriewerte bleiben davon ausgenommen.

## Grobe Zählerschritte und verzögerte Berichte (ab 0.2.7)

Growatt-Gesamtzähler können in 0,1-kWh-Schritten steigen, während Shelly-Zähler
kleinste Verbrauchsänderungen melden. Im normalen Snapshot-Modus sammelt SolarShare
daher mindestens fünf Minuten an einer gemeinsamen Messbasis. Passt die Bilanz
noch nicht, bleibt diese Basis bis zu einer Stunde erhalten. Der Status lautet
**Sammle Zählerwerte – warte auf gemeinsame Energiebilanz**. Es werden weder
Netzbezug noch Batterieenergie aus dem Wohnungsverbrauch erfunden. Auch bei kleinen
Wohnungsverbräuchen wird ein vollständig unveränderter Versorgungszähler nicht
als erfolgreiche Nullversorgung verbucht.

Nach einer erfolgreichen Bilanz werden die gesammelten Zählerdifferenzen einmalig
verteilt. Bereits veröffentlichte Summen bleiben während des Wartens erhalten;
das Intervall-Leistungsmittel ist bis zum nächsten abgeschlossenen Fenster unbekannt.
`pending_seconds` und `pending_balance` im Datenqualitätssensor zeigen die offene
Zeitspanne sowie Versorgung und Wohnungsverbrauch in kWh. Die Verteilung und
Autarkie sind Schätzungen über dieses gemeinsame Zeitfenster; zeitgleiche, exakt
gemessene Energieherkunft je Wohnung lässt sich aus groben Zählern nicht ableiten.

Fehlende/ungültige Quellen, mehr als fünf Minuten ohne SolarShare-Abtastung,
Neustarts, Tages- und PV-Nacht/Tagwechsel unterbrechen das Fenster weiterhin.
Daten aus diesen Lücken werden nicht nachgetragen. Rückläufige Zählerstände
werden auch während des Sammelns erkannt. Eine nach einer Stunde weiterhin
widersprüchliche Bilanz stoppt das Fenster mit der entsprechenden Fehlermeldung.
Gegenläufige Flüsse innerhalb eines Fensters werden als reale Gesamtverbrauchsmenge erfasst, aber deren Stromherkunft vorsichtshalber als ungeklärt ausgewiesen und nicht bepreist.
Die optionale strenge Berichtsprüfung behält ihre bisherige kurze Intervallprüfung.

## Erweiterung ab 0.3.0: Wallbox, Zähler, Tarife und Dashboard-Karte

Unter **SolarShare → Konfigurieren → Wallboxen** lassen sich Wallboxen mit
eigenen kumulativen kWh-Zählern (z. B. einem von EVCC bereitgestellten Gesamtzähler)
hinzufügen, ändern und pausieren. Jede Wallbox bekommt ein eigenes Home-Assistant-Gerät.
Die Wallbox darf nicht bereits über den Zähler einer Wohnung mitgemessen werden:
**Sonst würde derselbe Verbrauch doppelt in der Gebäudebilanz auftauchen.**
Für einzelne RFID-Ladekarten gibt es noch **keine** belastbare Zuordnung und Abrechnung.
Eine getrennt gemessene Wallbox kann weiterhin über EVCC betrieben werden.

Der Keller bzw. nicht einzeln gemessene Verbraucher benötigen **keinen**
fiktiven Zähler. Sie sind zusammen mit Messdifferenzen im Anlagenwert
**Allgemeinverbrauch und Messdifferenz** enthalten. Dieser Restwert ist kein
isoliert gemessener Kellerverbrauch.

Neu sind **Gemessener Verbrauch** (Heute / Monat / Jahr / Gesamt) pro Wohnung
und Wallbox. Diese Zählerwerte werden bei gültigen aufeinanderfolgenden
Messungen fortgeschrieben, auch wenn die gemeinsame PV-/Netzbilanz gerade
unklar ist. Bei echten Ausfällen oder Neustarts werden fehlende Zeiträume
ausdrücklich nicht rekonstruiert. Die alten zugeordneten Werte und die
bestehende SolarShare-Historie bleiben unverändert.

Unter **SolarShare → Konfigurieren → Strompreise** lassen sich
Solarstrom- und Netzstrompreis in **€/kWh** eingeben. Ohne eingegebene Preise
werden keine Kosten berechnet. Ab dann entstehen automatisch Sensoren
**Kosten zugeordnete Energie** für jede Wohnung/Wallbox. Sie enthalten nur
sicher zugeordnete Solar- und Netzenergie. Ungeklärte Herkunft wird
unter `unpriced_kwh` ausgewiesen. Ein angezeigter Betrag ist bei
`partial_amount: true` **nur ein Teilbetrag** und keine vollständige
Abrechnung. Tarifänderungen bepreisen nur zukünftige Messintervalle;
bereits gespeicherte Kosten werden nicht rückwirkend geändert. Grundpreise,
Netzentgelte und formelle Rechnungslegung sind noch nicht enthalten.

In **Erweiterte Einstellungen** kann die **Bilanztoleranz** (standardmäßig
0,15 kWh) an grob aktualisierende Zähler angepasst werden. Eine zugelassene
Unterschreitung der gemessenen Versorgung wird als **ungeklärte Energie**
und nicht als fiktiver Solar- oder Netzbezug geführt. Schalten Netz oder
Speicher in einem gemeinsamen Messfenster in beide Richtungen, bleibt der
Gesamtverbrauch erhalten; die Zuordnung seiner Herkunft bleibt ungeklärt.
Größere, unplausible Abweichungen unterbrechen weiterhin die
Herkunftsverteilung. Für die verbindliche Abrechnung sind geeignete
Messkonzepte und Prüfung der Messgrenzen notwendig.

### SolarShare-Karte über die ganze Seite

Nach Aktualisierung und vollständigem Neustart:

Ab **0.3.2** installiert SolarShare die mitgelieferte Dashboard-Karte und
registriert sie direkt beim Start mit bereits geladenem Lovelace bei standardmäßiger
Ressourcenverwaltung (**Storage/UI**) automatisch als JavaScript-Modul. Es ist keine zusätzliche HACS-Installation und
kein manueller Eintrag unter **Dashboard → Ressourcen** nötig. Bereits vorhandene
Einträge für dieselbe Karte werden aktualisiert statt doppelt angelegt;
andere Dashboard-Ressourcen bleiben unverändert.

1. Integration über HACS auf die neue Version aktualisieren und Home Assistant
   vollständig neu starten.
2. Im Dashboard eine **Panel-Ansicht (eine Karte)** anlegen.
3. **Karte hinzufügen → SolarShare** auswählen. Alternativ als manuelle Karte:

```yaml
type: custom:solarshare-card
period: month
```

Bei ausdrücklich per YAML verwalteten Ressourcen (`lovelace.resource_mode: yaml`)
ist eine automatische Änderung der Ressourcenliste technisch nicht möglich. In
diesem Fall unter `lovelace.resources` selbst hinzufügen:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /solarshare/solarshare-card.js?v=0.3.2
      type: module
```

Der Pfad ist bereits durch die Integration eingebunden. Nach einem Kartenupdate
die Home-Assistant-Seite neu laden (gegebenenfalls mit geleertem Browsercache).

Die Karte findet automatisch die SolarShare-Geräte und zeigt Wohnungen,
Wallboxen, gemessene kWh, zugeordnete Solar-/Netzanteile, ungeklärte
Energie und Kosten sowie die Gebäudewerte. Auf schmalen Displays bleibt die
Wohnungstabelle horizontal scrollbar. Die Karte ist für die **administrative
Gesamtansicht** vorgesehen. Sie darf nicht unverändert in für einzelne
Mieter zugänglichen Dashboards verwendet werden, da sie alle Einheiten zeigt.

**Vor dem Aktualisieren** die Home-Assistant-Konfiguration und
`.storage/solarshare.site.<entry_id>` sichern; den Integrationseintrag nicht löschen.
Die neuen Zähler müssen über **Konfigurieren** zugeordnet werden.

### Wenn „Custom element doesn't exist: solarshare-card“ erscheint

1. Über HACS **SolarShare 0.3.2 oder neuer** installieren und Home Assistant
   vollständig neu starten.
2. Unter **Einstellungen → Dashboards → Ressourcen** prüfen, ob **genau ein**
   Modul mit `/solarshare/solarshare-card.js?v=0.3.2` eingetragen ist.
3. Im gleichen Home-Assistant-System die Adresse
   `/solarshare/solarshare-card.js?v=0.3.2` aufrufen. Sie muss JavaScript statt
   einer 404- oder Login-Fehlerseite zeigen.
4. Dashboard neu laden, bei Bedarf Browsercache umgehen (Strg+F5).

Wird die Ressource bei **Storage/UI** noch nicht eingetragen, kann sie unter
**Dashboards → Ressourcen** einmal manuell mit dem oben genannten Pfad als
**JavaScript-Modul** ergänzt werden. Der Integrationseintrag und die
bereits aufgezeichneten Energie-/Kostenwerte müssen dafür nicht gelöscht werden.
Bei YAML-Ressourcen die Konfiguration wie oben beschrieben anpassen.

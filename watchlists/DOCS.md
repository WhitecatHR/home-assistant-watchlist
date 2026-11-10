# Watchlists 0.2 – Einrichtung und Grenzen

Eine **Home-Assistant-App (Add-on)** für zwei Personen mit experimentellen Anbieterimporten. Die lokale Film-/Serienverwaltung funktioniert unabhängig von diesen Importen. Es gibt keine kostenpflichtige Trakt-, SIMKL- oder Younify-Abhängigkeit. Strom, Speicherplatz und gegebenenfalls die eigene Hardware bleiben eure Kosten.

## Update auf 0.2.1

Auf 0.2.1 aktualisieren, Weboberfläche neu laden und Netflix/Prime unter Dienste erneut einlesen. Neu erkannte Anbieter-Titel erscheinen direkt mit ihren Quelldaten; eine Katalogzuordnung ist optional. Vorhandene Browser-Anmeldungen und manuelle Folgenstände werden nicht gelöscht. Frühere unbestätigte Importe bleiben unter „Frühere Importe prüfen“ erhalten und werden nicht als neue Watchlist vorausgesetzt.

In 0.2.0 konnte ein erfolgreicher Netflix-Verlauf bei fehlgeschlagener Watchlist Hunderte optionale Metadatenzeilen erzeugen. Diese Zahl ist keine Watchlist-Größe. Ab 0.2.1 ist die Sammelübersicht eingeklappt und enthält nur Titel mit bestätigter Watchlist-Beobachtung. Bei reinen Verlaufseinträgen bleibt die optionale Ergänzung im Titeldialog verfügbar. Die Netflix-Erkennung unterstützt zusätzlich die Listenüberschrift und Karten mit generierten Klassen; in Importdetails muss für die Merkliste `status: ok` stehen. Ein erfolgreicher Verlauf allein bestätigt die Watchlist nicht. Strukturierte Verlaufsdaten ersetzen beim neuen Einlesen die DOM-Verlaufsquelle, statt dieselben Folgen aus beiden Quellen zusammenzuführen. Frühere Verlaufseinträge werden nicht automatisch bereinigt.

„Merkliste“ und „Sehverlauf“ sind getrennte Ansichten. Staffel-/Folgezusätze werden für die optionale Zuordnung bereinigt. Filme lassen sich direkt aus der Anbieter-Liste verwalten oder im separaten Cinemeta-Filmkatalog suchen; dieser kann Originaltitel verwenden. Fehlende Metadaten verhindern die Anzeige eines importierten Titels nicht.

Bei fehlenden oder zusätzlichen Titeln unter Dienste → Importdetails prüfen, ob Merkliste und Verlauf erkannt wurden. Der Bericht enthält Bereichserkennung und Zähler, keine Cookies oder Anmeldetokens. Die App fällt bei unbekannten Listenbereichen nicht auf sämtliche Links einer Seite zurück.

## Was vorhanden ist

- Zwei umbenennbare Profile mit eigenen Listen und Fortschritten, lokal in SQLite.
- Seriensuche, Cover, Beschreibungen, Staffeln und Episoden über den öffentlichen TVmaze-Katalog.
- Direkte Anbieter-Titel mit Quellcovern ohne Katalogpflicht; separater Filmkatalog über Cinemeta und persönlicher Gesehen-Status für Filme.
- Antippen öffnet die Folgen; 550 ms Gedrückthalten öffnet Schnellaktionen. Scrollen bricht Gedrückthalten ab.
- Folgen einzeln oder gesammelt bis zu einer Folge markieren. Einzelmarkierungen lassen sich direkt rückgängig machen.
- Manuelle Dienstzuordnung, Pausieren, Abgeschlossen-Status und JSON-Datenexport.
- Zugriff über Home Assistant Ingress, ohne zusätzlichen offenen Port oder zweites Login.
- Ein im Add-on enthaltener Chromium-Browser, den ihr über die Oberfläche vom Tablet oder iPhone aus bedienen könnt.
- Acht getrennte Browserverzeichnisse: zwei Personen × vier Dienste. Es läuft höchstens ein Browser gleichzeitig.
- Manuell ausgelöste und optionale regelmäßige Leseversuche der Streaming-Webseiten.

## Ehrlicher Stand der automatischen Übernahme

| Dienst | Enthaltener Adapter | Noch zu prüfen |
| --- | --- | --- |
| Netflix | Merkliste und Sehverlauf über Webseiten | Anmeldung, Profilauswahl, aktuelle Seitenstruktur und Folgenzuordnung mit echten Konten |
| Prime Video | Merkliste und Sehverlauf über Webseiten | Region/Weiterleitungen, Seitenstruktur, Datenqualität und Anmeldung |
| Disney+ | Merkliste über Webseite | Anmeldung und Seitenstruktur; **kein automatischer Folgenstand in 0.1** |
| Crunchyroll | Merkliste und Sehverlauf über Webseiten | Anmeldung, aktuelle Profilauswahl und Folgen-/Fortschrittsdarstellung |

**Der Nutzer hat die Netflix-/Prime-Anmeldung bestätigt. Die Importüberarbeitung 0.2 benötigt noch einen Praxistest am Konto.** Parser wurden mit kontrollierten Beispielen geprüft; das beweist keine vollständige Übernahme beim Anbieter. Crunchyroll zeigt beim Nutzer eine Sicherheitsprüfung. Erkannte Sicherheitsprüfungen werden angezeigt und ein automatischer Importzeitplan angehalten; diese Sperren werden nicht umgangen. Disney+ ist noch nicht am Konto geprüft. Domainlisten sind begrenzt und können neue Anmeldedomains zunächst blockieren.

Die ausgewählten Streamingprofilnamen werden von euch bestätigt. Eine zuverlässige automatische Prüfung des gerade angemeldeten Profilnamens ist noch nicht implementiert. Bei erneutem Verbinden immer das richtige Profil auswählen.

Importe sind **ergänzend**: unvollständige oder fehlgeschlagene Leseversuche löschen keine lokalen Listen oder Fortschritte. Auch vom Anbieter entfernte Einträge werden in 0.2 noch nicht automatisch entfernt.

Neue Anbieter-Titel erscheinen direkt. Eine optionale Katalogzuordnung ergänzt weitere Episoden-/Coverdaten. Prime-Staffeln mit bereinigtem Seriennamen werden zusammengefasst; Netflix-Serien-IDs erlauben die Zuordnung mehrerer Folgen zu einer Serie. Bei unbekannten Typen werden gleichnamige, unterschiedliche Anbieter-IDs nicht als sicher identischer Film/Serie angenommen.

Netflix-Verlaufsantworten können Titel, Folgenname, Zeit und Wiedergabeposition liefern. Eine begrenzte Metadatenabfrage im bereits angemeldeten Netflix-Browser kann zusätzlich Staffel/Folge liefern. Fehlen diese Daten oder antwortet die Website nicht wie erwartet, bleibt der Stand unbekannt. Es wird keine vollständige Historie oder lückenlose Episodenzählung behauptet. Direkte Titel erlauben persönliche Folgenstandkorrekturen auch ohne Katalog; manuelle Eingaben haben Vorrang.

Eine Anzeige im Verlauf beweist nicht, dass eine Folge vollständig gesehen wurde. Automatisch als gesehen markiert wird nur, wenn Staffel/Folge eindeutig zugeordnet sind und die Webseite einen numerischen Fortschritt von mindestens 90 % liefert. Ansonsten erscheint die Beobachtung mit unbekanntem Abschluss. Manuelle Markierungen haben Vorrang. Unterschiedliche Anime-Staffelzählungen müssen gegebenenfalls manuell korrigiert werden.

Eine manuelle Dienstzuordnung in Watchlists schreibt **nicht** in die Merkliste bei Netflix, Prime, Disney+ oder Crunchyroll. Importierte Merkliste und bloßer Sehverlauf werden getrennt gekennzeichnet.

## Voraussetzungen

- Home Assistant OS mit Supervisor (bei eurem System bestätigt).
- Hardwarearchitektur `amd64` oder `aarch64`; die konkrete Architektur eures Rechners wurde noch nicht ausgelesen.
- Freier Platz für ein größeres Chromium-Containerimage und Browserprofile. Den zusätzlichen RAM-Bedarf auf eurem Gerät im Praxistest prüfen; es läuft nur ein Browser zur selben Zeit.
- Internet für TVmaze, Cover und die Streaming-Webseiten. Bereits geladene Katalogdaten, Listen und Fortschritte bleiben lokal verfügbar; Cover werden vom Bildanbieter geladen und sind offline nicht garantiert sichtbar.

## Installation

Die ZIP ist ein **Quellcodepaket**, keine direkt in Home Assistant hochladbare Add-on-Datei.

**Empfohlener Weg für Tablet/iPhone:** [Repository in Home Assistant hinzufügen](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWhitecatHR%2Fhome-assistant-watchlist). Alternativ unter Einstellungen → Apps/Add-ons → Store → Menü → Repositorys die URL `https://github.com/WhitecatHR/home-assistant-watchlist` eintragen. Danach „Watchlists“ installieren und starten. Der erste Containerbuild lädt unter anderem Chromium und kann mehrere Minuten dauern.

Der Supervisor muss das Repository ohne euren Browserlogin lesen können. Für diesen Installationsweg muss das Repository auf GitHub öffentlich sein. Solange es privat ist, funktioniert der einfache Hinzufügen-Link ohne zusätzliche Git-Zugangsdaten nicht. Zugangsdaten gehören nicht in dieses Repository oder in öffentlich geteilte URLs.

**Für vorhandenen Dateizugriff/Terminal:** Den Ordner `watchlists` nach `/addons/watchlists` auf dem HA-Rechner kopieren. Dann im Store nach lokalen Apps/Add-ons suchen, neu laden und installieren. Eine lokale ZIP allein erledigt diesen Schritt nicht.

Nach dem Start „Weboberfläche öffnen“ und bei Bedarf „In Seitenleiste anzeigen“ aktivieren. Die App verwendet ausschließlich Ingress. Es muss kein Port ins Heimnetz oder Internet freigegeben werden.

## Erste Schritte

1. Oben „Person 1“ auswählen. Unter „Dienste“ den Profilnamen ändern. Danach das zweite Profil entsprechend benennen.
2. Über „+“ eine Serie suchen, das richtige Erscheinungsjahr prüfen und einen Dienst zuordnen. Folgenstände lassen sich sofort pflegen.
3. Unter „Dienste“ bei einem Anbieter „Verbinden“ drücken. Im Bild die offizielle Anbieter-Seite selbst bedienen.
4. Für Eingaben zuerst das gewünschte Feld im Bild antippen. Den Text darunter eingeben und „Senden“ drücken. „Nächstes Feld“, „Enter“, Scrollen und Zoom stehen zur Verfügung. Passwort, E-Mail und Einmalcodes werden nicht in der App-Datenbank gespeichert.
5. Das richtige Anbieterprofil auswählen, dessen Namen unten eintragen und bestätigen. Regelmäßige Importe sind zunächst aus; nur nach erfolgreichem Test einschalten.
6. „Jetzt einlesen“ starten. Die Merkliste zeigt bestätigte Anbietertitel direkt; „Katalogdaten ergänzen“ ist optional. In „Importdetails“ die getrennten Zähler für Merkliste und Verlauf prüfen.
7. Für die zweite Person separat anmelden. Die Browserverzeichnisse sind getrennt.

Der Anmeldebrowser schließt nach fünf Minuten ohne Bedienung. Eine geschlossene Oberfläche beendet die Website-Anmeldung nicht: Cookies verbleiben im lokalen Browserverzeichnis, bis „Trennen“ gewählt wird. Das laufende Browserfenster wird bei Dialogende geschlossen.

## Optionen

- `sync_interval_minutes`: 60–1440 Minuten, Standard 360. Wird nur für einzeln aktivierte Verbindungen verwendet. Nach einer Änderung Add-on neu starten.
- `browser_enabled`: Standard `true`. Bei `false` funktionieren Serienverwaltung und Folgenstände weiter, Browseranmeldungen und Importe sind deaktiviert.

## Daten und Zugriff

- Datenbank: `/data/watchlists/watchlists.sqlite`.
- Anmeldesitzungen: `/data/watchlists/.sessions/`. Diese enthalten sensible Cookies und können Bestandteil eines HA-Backups sein. Das Add-on verschlüsselt Browserprofile nicht zusätzlich.
- JSON-Export enthält Haushaltseinträge, Zuordnungen und Beobachtungen, **keine Cookies oder Passwörter**. Ein Wiederherstellen dieses Exports über die Oberfläche ist in 0.1 noch nicht implementiert; vollständige Wiederherstellung über HA-Add-on-Backups.
- Beide Profile sind für berechtigte HA-Nutzer mit Zugriff auf diese Add-on-Oberfläche zugänglich. Zwei Fortschritte bedeuten hier **keine gegenseitige Zugriffssperre**. HA-Benutzernamen werden nicht automatisch auf Profile abgebildet.
- Das Add-on braucht weder Supervisor-Token noch Zugriff auf die Home-Assistant-Konfiguration, Host-Netzwerk, Docker-Socket oder privilegierten Modus.
- Der Dienst akzeptiert produktiv ausschließlich den echten Ingress-TCP-Peer `172.30.32.2`, keine vom Client behaupteten Proxy-IP-Header. Schreibzugriffe brauchen einen eigenen Anwendungsheader.
- Chromium läuft als eigener Linux-Nutzer. Sein interner Sandboxmodus ist wegen der eingeschränkten Add-on-Containerumgebung deaktiviert; die äußere Containerisolation bleibt aktiv. Die Domainlisten begrenzen Browseranfragen. Einen neuen Anmeldedienst erst nach Prüfung ergänzen.
- Nicht in einem ungeschützten Browserfenster offen lassen: Die Anmeldeansicht zeigt echte Streamingkonten.

## Entwicklung und Prüfungen

Python 3.12 oder neuer. Abhängigkeiten stehen in `requirements.txt`. Für lokale Entwicklung kann `create_app(data=..., standalone=True)` verwendet werden; produktiv ist dieser Modus standardmäßig aus. Kein eigener ungeschützter Standalone-Port wird als Add-on veröffentlicht.

Die Testausführung steht unter `tests/`. Sie prüft unter anderem Profiltrennung, Datenbank-Neustart, manuelle Korrekturen gegenüber Importen, Leer-/Fehlerimporte, Domainbeschränkungen, Ingressschutz, Datenexport und touchbezogene UI-Ereignisse. Sie ersetzt weder den Container-/Supervisor-Test auf eurem HA-Rechner noch echte Anbieteranmeldungen oder einen Test auf euren physischen Geräten.

## Quellen und Lizenz

Eigener Anwendungscode: MIT, siehe `LICENSE` im Repository. Seriendaten: [TVmaze API](https://www.tvmaze.com/api), [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/). Optionaler Filmkatalog: [Cinemeta](https://github.com/Stremio/cinemeta). Quellcover und Anbieterdaten bleiben beim jeweiligen Rechteinhaber. Dieses Projekt ist weder von Home Assistant noch den Streaminganbietern beauftragt oder zertifiziert.

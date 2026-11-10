# Watchlists für Home Assistant

Quellcode einer selbst betriebenen Home-Assistant-App für zwei persönliche Film- und Serienprofile. Enthält Touchoberfläche, direkte Anbieterlisten mit Covern, optionale Katalogdaten, SQLite-Speicherung und einen lokalen Anmeldebrowser mit experimentellen Websiteimporten.

**Version 0.2 zeigt neu eingelesene Anbieter-Titel ohne manuelle Katalogzuordnung.** Serien-/Staffelzusätze werden bereinigt, Filme separat unterstützt und Sehverlauf und Merkliste getrennt. Die aktualisierten Anbieteradapter sind noch keine bestätigte Komplettsynchronisierung aller vier Dienste. Siehe [Änderungen](watchlists/CHANGELOG.md) und [Einrichtung und Grenzen](watchlists/DOCS.md).

**Update von 0.1:** Add-on auf 0.2.0 aktualisieren, Weboberfläche neu laden und unter Dienste Netflix/Prime erneut einlesen. Vorhandene Anmeldungen und manuelle Fortschritte bleiben erhalten. Frühere unbestätigte Importe werden unter „Frühere Importe prüfen“ angezeigt. Bei Fehlversuchen helfen die neuen „Importdetails“.

## Installation aus Home Assistant

**Voraussetzung:** Das Repository muss für den Home-Assistant-Supervisor lesbar sein. Für die einfache Installation ohne zusätzliche Git-Zugangsdaten muss es auf GitHub öffentlich sein. Ein Login in GitHub auf dem iPhone gibt dem Supervisor keinen Zugriff auf ein privates Repository.

1. [Repository in Home Assistant hinzufügen](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWhitecatHR%2Fhome-assistant-watchlist).
2. Im Store **Watchlists** auswählen und installieren. Das Containerimage mit Chromium wird auf dem HA-Rechner gebaut; der erste Build kann mehrere Minuten dauern.
3. Starten → **Weboberfläche öffnen**. Bei Bedarf **In Seitenleiste anzeigen** aktivieren.
4. Beide Profile benennen und zuerst die lokale Serienverwaltung ausprobieren. Anbieteranmeldungen danach einzeln prüfen.

Manuell lässt sich diese URL unter Einstellungen → Apps/Add-ons → Store → Menü → Repositorys hinzufügen:

```text
https://github.com/WhitecatHR/home-assistant-watchlist
```

Die Repositorystruktur ist `repository.yaml` im Stamm und die App im Unterordner `watchlists/`. Der Docker-Build benötigt keine BuildKit-spezifischen `RUN --mount`-Funktionen.

Die separat bereitgestellte Vorschau verwendet ausschließlich ausdrücklich gekennzeichnete Beispieldaten und speichert sie nur im jeweiligen Browser. Das installierte Add-on verwendet eine gemeinsame lokale Datenbank auf dem HA-Rechner.

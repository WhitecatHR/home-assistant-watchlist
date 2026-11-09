# Watchlists für Home Assistant

Quellcode einer experimentellen, selbst betriebenen Home-Assistant-App für zwei persönliche Serienprofile. Enthält Touchoberfläche, Cover-/Episodenkatalog, SQLite-Speicherung und einen lokalen Anmeldebrowser mit experimentellen Websiteimporten.

**Version 0.1 ist ein geprüfter Entwicklungsstand, keine bestätigte Komplettsynchronisierung der vier Streamingdienste.** Sie wurde noch nicht auf dem Zielgerät installiert. Siehe [Einrichtung und Grenzen](watchlists/DOCS.md).

## Installation aus Home Assistant

**Voraussetzung:** Das Repository muss für den Home-Assistant-Supervisor lesbar sein. Für die einfache Installation ohne zusätzliche Git-Zugangsdaten muss es auf GitHub öffentlich sein. Ein Login in GitHub auf dem iPhone gibt dem Supervisor keinen Zugriff auf ein privates Repository.

1. [Repository in Home Assistant hinzufügen](https://my.home-assistant.io/redirect/supervisor_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWhitecatHR%2Fhome-assistant-watchlist).
2. Im Store **Watchlists** auswählen und installieren. Das Containerimage mit Chromium wird auf dem HA-Rechner gebaut; der erste Build kann mehrere Minuten dauern.
3. Starten → **Weboberfläche öffnen**. Bei Bedarf **In Seitenleiste anzeigen** aktivieren.
4. Beide Profile benennen und zuerst die lokale Serienverwaltung ausprobieren. Anbieteranmeldungen danach einzeln prüfen.

Manuell lässt sich diese URL unter Einstellungen → Apps/Add-ons → Store → Menü → Repositorys hinzufügen:

```text
https://github.com/WhitecatHR/home-assistant-watchlist
```

Die Repositorystruktur ist `repository.yaml` im Stamm und die App im Unterordner `watchlists/`. Der Docker-Build benötigt keine BuildKit-spezifischen `RUN --mount`-Funktionen.

Die separat bereitgestellte Vorschau verwendet ausschließlich ausdrücklich gekennzeichnete Beispieldaten und speichert sie nur im jeweiligen Browser. Das installierte Add-on verwendet eine gemeinsame lokale Datenbank auf dem HA-Rechner.

# Prüfstand 0.2.1

Stand: 10. November 2026.

- Python-Backend: 48 automatisierte Prüfungen bestanden. Neue Regressionen in 0.2.1: fehlgeschlagene Watchlist bei erfolgreichem Verlauf ausdrücklich gemeldet, strukturierter Netflix-Verlauf ersetzt DOM-Verlauf ohne doppelte Folgen, Quellenpriorität beeinflusst weder Watchlist noch andere Anbieter. Weiterhin geprüft: Profiltrennung, direkte Titel ohne Katalog, Staffel-/Folgetitel, Filme, manuelle Korrekturen, Datenmigration, Ingressschutz und Sicherheits-/Profil-/Weiterleitungsblockaden.
- DOM-/Interaktionsprüfung: 21 Prüfbereiche bestanden. Neu: Netflix-Liste mit generierten Klassen ohne Galeriecontainer, deutsch-/englischsprachige Listenüberschrift, doppelte Kartenlinks zusammengefasst, beschriftete leere Liste, falsche Route abgelehnt, 490 reine Verlaufseinträge aus der Metadatenübersicht ausgeschlossen, optionale Watchlist-Metadaten eingeklappt und Metadaten im einzelnen Verlaufstitel weiter verfügbar. Weiterhin Cover, zwei Profile, Folgenbearbeitung, Tippen/Halten, Scroll-Abbruch, Filmstatus, CSS und Escaping geprüft.
- Dockerimage für amd64: Der Build der Basisversion 0.2.0 und alle damaligen 45 Backendtests im Container waren erfolgreich. Für den Patch 0.2.1 wurde kein neuer Imagebuild ausgeführt; Abhängigkeiten und Startskript sind unverändert. Der Proxy-Zertifikats-Mount existiert nur in einer temporären Test-Dockerfile außerhalb des Repositorys.
- YAML-/JSON-Konfiguration, JavaScript-/Python- und Shell-Syntax geprüft.

**Vom Nutzer bestätigt:** Add-on auf dem HA-Rechner installiert; Netflix- und Prime-Anmeldung funktionieren. Importdiagnose aus 0.2.0: Netflix-Watchlist fehlgeschlagen (66 Titel-Links, kein erkannter Galeriecontainer), Verlauf erfolgreich mit DOM- und JSON-Daten zusammengeführt (888 Einträge); 490 Titel erschienen in der optionalen Metadatenübersicht. Diese Zahlen sind keine bestätigte Watchlist-Größe. Weiterhin gemeldet: Staffel-/Folgetitel bei Zuordnungen, fehlende Filme und Folgenstände sowie Crunchyroll-Sicherheitsprüfung.

**Noch nicht geprüft:** Live-Import der angepassten Netflix-Bereichserkennung aus 0.2.1 am Konto, vollständige/korrekte Übernahme von Merkliste und Folgenständen aller Anbieter, Disney+, visuelles Rendering im Browser und physische Touchgeräte, aarch64-Imagebuild. Eine erkannte Crunchyroll-Sperre wird angezeigt und stoppt automatische Importversuche; sie wird nicht umgangen.

Die Browseradapter sind experimentell. Kontrollierte Parserbeispiele sind kein Nachweis funktionierender Anbieterintegration. Die Websitevorschau ist ausdrücklich eine Demo mit erfundenen Profilen/Fortschritten; das Add-on verwendet dagegen die lokale HA-Datenbank.

Die Installationsquelle ist `https://github.com/WhitecatHR/home-assistant-watchlist`. Für den einfachen HA-Store-Zugriff muss sie öffentlich lesbar sein. Der veröffentlichte Dockerfile verwendet den normalen Docker-Build ohne BuildKit-spezifische Mounts. Im verwalteten Testsystem wird ausschließlich für dessen Proxy-Zertifikat eine temporäre, nicht veröffentlichte BuildKit-Variante verwendet; das Zertifikat wird nicht in das Image kopiert.

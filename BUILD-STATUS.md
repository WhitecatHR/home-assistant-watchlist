# Prüfstand 0.2.0

Stand: 10. November 2026.

- Python-Backend: 45 automatisierte Prüfungen. Neue Fälle: direkte Watchlist-Anzeige ohne Katalogzuordnung, „Dr. House“ mit Folgentitel, Prime-Staffelzusätze, Filme und persönliche Gesehen-Stände, gleichnamiger Film/Serie, gruppierte Zuordnung, Reparatur widersprüchlicher alter Medientypen, neueste Folgenposition unabhängig von Importreihenfolge, aktuelle Netflix-Metadatenposition ohne Aufrunden an der Gesehen-Schwelle, manuelle Korrekturen, echte alte Datenbankspalten sowie Sicherheits-/Profil-/Weiterleitungsblockaden.
- DOM-/Interaktionsprüfung: Cover, zwei Profile, Folgen abhaken, Suche, Tippen/Halten, Scroll-Abbruch, Ausschluss von Empfehlungen, Ablehnung unbekannter Listenbereiche, Sicherheitsprüfung, native Titel ohne Katalog, getrennte Merkliste/Verlauf/Altimporte, Filmstatus und persönlicher Folgenstand.
- Dockerimage für amd64: Build erfolgreich; alle 45 Backendtests zusätzlich im gebauten Container bestanden. Der Proxy-Zertifikats-Mount existiert nur in einer temporären Test-Dockerfile außerhalb des Repositorys.
- YAML-/JSON-Konfiguration, JavaScript-/Python- und Shell-Syntax geprüft.

**Vom Nutzer bestätigt:** 0.1 ist auf dem HA-Rechner installiert; Netflix- und Prime-Anmeldung funktionieren. Gemeldete Probleme: überzählige/fehlende Watchlist-Titel, Staffel-/Folgetitel bei Zuordnungen, fehlende Filme und Folgenstände sowie Crunchyroll-Sicherheitsprüfung.

**Noch nicht geprüft:** Live-Import der überarbeiteten 0.2-Adapter an diesen Konten, Disney+, visuelles Rendering im Browser und physische Touchgeräte, aarch64-Imagebuild. Eine erkannte Crunchyroll-Sperre wird angezeigt und stoppt automatische Importversuche; sie wird nicht umgangen.

Die Browseradapter sind experimentell. Kontrollierte Parserbeispiele sind kein Nachweis funktionierender Anbieterintegration. Die Websitevorschau ist ausdrücklich eine Demo mit erfundenen Profilen/Fortschritten; das Add-on verwendet dagegen die lokale HA-Datenbank.

Die Installationsquelle ist `https://github.com/WhitecatHR/home-assistant-watchlist`. Für den einfachen HA-Store-Zugriff muss sie öffentlich lesbar sein. Der veröffentlichte Dockerfile verwendet den normalen Docker-Build ohne BuildKit-spezifische Mounts. Im verwalteten Testsystem wird ausschließlich für dessen Proxy-Zertifikat eine temporäre, nicht veröffentlichte BuildKit-Variante verwendet; das Zertifikat wird nicht in das Image kopiert.

# Prüfstand 0.1.0

Stand: 9. November 2026.

- Python-Backend: 22 automatisierte Prüfungen, unter anderem Profiltrennung, Neustart, Fortschrittslücken, sichere Titelzuordnung, manuelle Korrekturen, ergänzende Importe, Export ohne Sitzungsdaten, Ingress-TCP-Peer, Browseraktionsgrenzen und Optionen.
- DOM-/Interaktionsprüfung: Coverdarstellung, zwei Profile, Folgen abhaken, Suche/Hinzufügen, Tippen, 550-ms-Halten, Unterdrücken des anschließenden Klicks, Abbruch durch Scrollen/Pointer-Cancel, CSS-Parsing und Text-Escaping.
- Dockerimage für amd64: erfolgreich gebaut; Backendtests zusätzlich innerhalb des gebauten Containers ausgeführt. Ein erster Versuch musste wegen des begrenzten VFS-Testlaufwerks bereinigt werden. Die eigenen Testartefakte wurden anschließend entfernt; kein fremder Docker-Bestand wurde bereinigt.
- YAML-/JSON-Konfiguration, JavaScript-/Python- und Shell-Syntax geprüft.

**Nicht geprüft:** visuelles Rendering in einem echten Browser, tatsächliche Installation/Ingress auf dem Home-Assistant-Zielgerät, aarch64-Imagebuild, physische Touchgeräte sowie Anmeldung und Import bei Netflix, Prime Video, Disney+ oder Crunchyroll.

Die Browseradapter sind experimentell. Kontrollierte Parserbeispiele sind kein Nachweis funktionierender Anbieterintegration. Die Websitevorschau ist ausdrücklich eine Demo mit erfundenen Profilen/Fortschritten; das Add-on verwendet dagegen die lokale HA-Datenbank.

Die Installationsquelle ist `https://github.com/WhitecatHR/home-assistant-watchlist`. Für den einfachen HA-Store-Zugriff muss sie öffentlich lesbar sein. Der veröffentlichte Dockerfile verwendet den normalen Docker-Build ohne BuildKit-spezifische Mounts. Im verwalteten Testsystem wird ausschließlich für dessen Proxy-Zertifikat eine temporäre, nicht veröffentlichte BuildKit-Variante verwendet; das Zertifikat wird nicht in das Image kopiert.

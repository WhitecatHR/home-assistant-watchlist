# 0.2.0

- Anbieter-Watchlists erscheinen direkt, ohne vorgeschaltete Katalogzuordnung; Cover werden auch aus der Quelle übernommen.
- Filme werden unterstützt: direkter Anbieterimport, persönlicher Gesehen-Status und optionaler Filmkatalog über Cinemeta.
- Staffel- und Folgezusätze werden für Zuordnungen bereinigt; „Dr. House“ wird als „House“ gesucht. Prime-Staffeln desselben Titels teilen eine Zuordnung.
- Merkliste, Sehverlauf und frühere unbestätigte Importe sind getrennt filterbar. Empfehlungen außerhalb erkannter Listenbereiche werden ausgeschlossen; Weiterleitungen auf Startseiten brechen den Bereichsimport ab.
- Netflix-Verlaufsantworten können Serien-/Folgentitel, Wiedergabepositionen und Metadaten liefern. Fehlende Folgenstände bleiben unbekannt und können persönlich korrigiert werden.
- Sicherheitsprüfungen werden angezeigt; bei erkanntem Anbieterblock wird der Zeitplan angehalten. Keine Umgehung von Captchas oder Zugangssperren.
- Importdetails zeigen Bereichserkennung und Zähler ohne Cookies oder Tokens.
- Datenmigration erhält frühere Einträge, manuelle Fortschritte und Browser-Anmeldungen. Altimporte aus 0.1 werden zur Prüfung gekennzeichnet; nach dem Update neu einlesen.
- Mit kontrollierten Beispielen geprüft; der aktualisierte Import benötigt weiterhin einen Praxistest mit den Konten.

# 0.1.0

- Zwei Profile mit eigenen Listen und Fortschritten, Seriensuche und Covern.
- Touchoberfläche mit Tippen, Gedrückthalten, Einzel- und Sammelmarkierungen.
- Home Assistant Ingress und lokale SQLite-Speicherung.
- Lokaler Anmeldebrowser mit isolierten Sitzungen, optionaler Zeitplan und ergänzende Beobachtungsimporte.
- Experimentelle Adapter für Netflix/Prime/Crunchyroll (Merkliste + Verlauf) und Disney+ (Merkliste).
- Explizite Zuordnung unklarer Titel und Schutz manueller Fortschrittskorrekturen.
- Keine Anbieteranmeldung oder vollständige Synchronisierung als getestet ausgewiesen.

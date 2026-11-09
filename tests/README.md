# Prüfungen

Backend (nach Installation von `watchlists/requirements.txt`):

```sh
python -m unittest discover -s tests -v
```

DOM-/Interaktionsprüfungen mit Node.js 22 oder neuer:

```sh
cd tests
npm install
npm test
```

Die Beispieldaten in `preview/demo-data.json` stammen aus dem öffentlichen TVmaze-Katalog. Die Preview-Personen Alex und Sam und deren Fortschritte sind erfunden.

Die DOM-Prüfung ist kein visueller Browsertest. Echte Anbieteranmeldungen, aktuelle Kontoseiten, die Home-Assistant-Installation sowie physische iPhone-/Tablet-Tests sind gesonderte Praxistests.

# Validierung der Sonar-Erweiterung

- Alle 13 lokalen Tests inklusive Copier-Rendering erfolgreich; Workflows mit actionlint geprüft.

- Tests prüfen URL-Validierung, Ablehnung der entfernten Konfigurationsaktionen,
  fehlende Sonar-Tokens vor der Anlage und unveränderte bestehende Repositories.
- Sonar-Einstellungen werden ausschließlich nach erfolgreicher Neuanlage und vor
  dem ersten Push gesetzt. Der Token wird nur über stdin übergeben.
- Fehlerausgaben enthalten keinen Token; Konfigurationsfehler verhindern den Push.
- GitHub-Aufrufe in den Tests sind gemockt. Ein echter Sonar-Token wird nicht verwendet.
- Ein echter End-to-End-Durchlauf benötigt das Factory-Secret SONAR_TOKEN und eine
  gültige SONAR_HOST_URL. Der Prüfworkflow prüft Vorhandensein, nicht Token-Gültigkeit.

## JDK-Template

- 17 lokale Tests erfolgreich, einschließlich JDK-Rendering für Java 17/21/25,
  optionalem SAST, deaktivierter CI und Kompilieren/Ausführen der Java-Anwendung.
- Factory- und gerenderte JDK-Workflows mit actionlint geprüft.
- Die Factory-CI baut das generierte Maven-Projekt mit Java 17/21/25 und prüft
  die PolyScan-Integration mit Java 21. PolyScan ist auf v16.1.1 per Commit festgelegt.

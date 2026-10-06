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

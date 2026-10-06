# Validierung der Erweiterung

- 12 lokale Tests für Formularvalidierung, Dispatcher, Berechtigungen,
  Variablenkonfiguration, Secret-Erzeugung, bestehende Secrets und vertrauliche
  Fehlermeldungen erfolgreich. GitHub-Aufrufe sind dabei gemockt.
- Bestehende Workflows und neuer Konfigurations-Prüfworkflow mit `actionlint` geprüft.
- Der ursprüngliche Repository-Erstellungsablauf wurde vom Benutzer auf GitHub
  erfolgreich getestet.
- Der vollständige Copier-Integrationstest und die neuen GitHub-End-to-End-Aktionen
  konnten lokal nicht ausgeführt werden: PyPI ist aus der Sandbox nicht erreichbar.
  Die Tests bleiben im GitHub-Actions-Testworkflow enthalten.

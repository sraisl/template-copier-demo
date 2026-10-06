# Lokale Prüfung

- Fünf Tests für Eingabevalidierung, Berechtigungen, bestehende Ziel-Repositories und Token-Zielkonto erfolgreich.
- GitHub-Actions-Workflows mit `actionlint` geprüft.
- YAML-Dateien und Jinja-Renderings der Python-/Workflow-Dateien geprüft.
- Vollständiger Copier-Integrationstest vorhanden, aber hier nicht ausführbar:
  PyPI ist aus dieser Umgebung nicht erreichbar; Copier konnte nicht installiert werden.
- GitHub-End-to-End-Test und Veröffentlichung offen: Die vorhandene CLI-Anmeldung
  ist ungültig. Außerdem ist das Anlegen von `.git` in dieser Arbeitsmappe durch
  die Dateisystemrichtlinie gesperrt. Projektdateien sind vollständig angelegt;
  die Initialisierungs- und Upload-Befehle stehen in der README.

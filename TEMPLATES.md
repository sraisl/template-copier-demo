# Templates mit Copier

Copier erzeugt Repository-Dateien aus Vorlagen und ausgewählten Optionen.
Die GitHub-Issue-Formulare sind der Einstieg für diese Optionen.

## Ablauf

1. Ein Issue mit `[repo]` im Titel startet `.github/workflows/issue-actions.yml`.
2. `scripts/automation.py` prüft Schreibrechte und Formularwerte.
3. Der Dispatcher wählt `templates/python`, `templates/jdk` oder `templates/universal`
   und übergibt die Optionen als `data` an `copier.run_copy(...)`.
4. Copier rendert das Unterverzeichnis `project` in ein temporäres Zielverzeichnis.
5. `preview` stellt die Dateien als Workflow-Artefakt bereit. `create` erstellt ein
   neues GitHub-Repository, setzt gegebenenfalls Sonar-Einstellungen und pusht die Dateien.
6. Der Workflow kommentiert das Ergebnis und schließt das erfolgreiche Issue.

## Aufbau eines Templates

- `copier.yml` definiert Variablen, Datentypen, Standardwerte und Auswahlmöglichkeiten.
  `_subdirectory: project` legt fest, welcher Ordner kopiert wird.
- Dateien mit `.jinja` werden gerendert; die Endung entfällt im Ziel.
  Beispielsweise wird `{{ java_version }}` durch die Java-Auswahl ersetzt.
- Jinja kann auch Pfade steuern: `{% if include_ci %}.github{% endif %}` erzeugt
  den Workflow-Ordner nur bei aktivierter CI. Leere Pfade werden ausgelassen.
- `{% if include_sast %}` erzeugt den SAST-Job nur bei entsprechender Auswahl.
- GitHub-Ausdrücke wie `${{ secrets.SONAR_TOKEN }}` stehen in Jinja-Dateien in
  `{% raw %}…{% endraw %}`, damit Copier sie unverändert übernimmt.

## Die drei Vorlagen

| Vorlage | Optionen | Erzeugtes Repository |
| --- | --- | --- |
| Python | Python 3.11/3.12/3.13, CI | Anwendung, Test, `pyproject.toml`, README, optionale Workflows |
| JDK | Java 17/21/25, CI, SAST | Maven-Projekt, JUnit-Test, README; optional Checkout, Setup-Java und PolyScan |
| Universal | Ein oder mehrere Typen, externer Workflow-Verweis | Ausschließlich `.github/workflows/ci.yml` mit einem Reusable-Workflow-Aufruf |

Universal unterstützt `node`, `docker`, `spring-boot` und `spring-boot-buildpack`.
Die Auswahl wird als JSON-String übergeben, beispielsweise `types: '["node","docker"]'`.
Der externe Reusable Workflow wird nicht erstellt. Sein Standardverweis im Formular
ist `sraisl/reusable-workflows/.github/workflows/ci.yml@main`.

Python und JDK erzeugen `.copier-answers.yml` mit den Template-Antworten.
Universal erzeugt diese Datei nicht, damit ausschließlich der Caller im Ziel liegt.

Bei Universal wählt das Formular `JDK_HOME` aus `/opt/jdk-21`, `/opt/jdk-25`
und `/opt/jdk-17`. Bei `create` wird die Auswahl vor dem ersten Push als
Actions-Variable im neuen Repository gesetzt und kann über `vars.JDK_HOME`
verwendet werden. Ältere Issues ohne dieses Feld verwenden `/opt/jdk-21`.
Bei `preview` werden keine Repository-Variablen gesetzt.

## Sonar und Secrets

Bei aktivierter Sonar-Option setzt die Automation ausschließlich im **neuen** Repository
`SONAR_HOST_URL` als Actions-Variable und `SONAR_TOKEN` als Actions-Secret.
Die URL stammt aus dem Issue; der Token aus dem Secret des Factory-Repositories
`template-copier-demo`. Secrets sind keine Copier-Variablen und landen nicht in Dateien.

Universal gibt den Token per `jobs.ci.secrets.SONAR_TOKEN` weiter. Der externe Workflow
muss dieses Secret deklarieren und kann die URL über `vars.SONAR_HOST_URL` verwenden.
Ein vorhandenes Ziel-Repository wird abgelehnt; `preview` verändert keine GitHub-Einstellungen.

## Änderungen

Formulare liegen in `.github/ISSUE_TEMPLATE/`, Vorlagen in `templates/` und
Validierung sowie Variablenübergabe in `scripts/automation.py`. Neue Optionen müssen
an diesen Stellen abgestimmt werden. Formular-Defaults (`value`/`default`) und
Copier-Defaults (`default` in `copier.yml`) sind getrennte Einstellungen.
Änderungen wirken auf künftig erzeugte Repositories; bestehende werden nicht aktualisiert.

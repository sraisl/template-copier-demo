# GitHub Issues × Copier – Repository Factory

Ein Demo-Repository als Self-Service-Einstieg: Issue öffnen, Optionen auswählen,
Workflow erzeugt ein passendes Python-Projekt und legt auf Wunsch ein neues
GitHub-Repository an. Das Copier-Template liegt direkt in diesem Repository.

```mermaid
flowchart LR
    A[Issue-Formular] --> B[Berechtigung und Eingaben prüfen]
    B --> C[Copier rendert Python-Template]
    C --> D{Aktion}
    D -->|preview| E[ZIP-Artefakt im Workflow]
    D -->|create| F[GitHub-Repository erstellen und pushen]
    E --> G[Issue-Kommentar und Issue schließen]
    F --> G
```

## Demo lokal ausprobieren

Voraussetzungen: Python ab 3.11 und [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run python scripts/automation.py --body examples/preview.md --output output/demo-service
cd output/demo-service
python main.py
python -m unittest discover -s tests
```

Die lokale Ausführung erzeugt ausschließlich Dateien – auch wenn im Beispiel
`create` ausgewählt ist. Ein frisches Zielverzeichnis verwenden.

## Auf GitHub starten

Dieses Projekt als neues Repository hochladen (die GitHub CLI muss angemeldet sein):

```sh
git init -b main
git add .
git commit -m "Add issue-driven Copier demo"
gh repo create template-copier-demo --private --source=. --remote=origin --push
```

Actions müssen aktiviert sein. Unter **Issues → New issue → Repository mit Copier
 erstellen** eine Anfrage erstellen. Für den ersten Durchlauf `preview` wählen.
Nach erfolgreicher Verarbeitung enthält der Kommentar einen Link zum Workflow;
dort steht das Artefakt `copier-preview` zum Download bereit. Vorschauen benötigen
kein zusätzliches Secret.

Für `create` unter **Settings → Secrets and variables → Actions** konfigurieren:

| Einstellung | Bedeutung |
| --- | --- |
| Secret `REPO_FACTORY_TOKEN` | Token mit Berechtigung zum Erstellen und Befüllen der Ziel-Repositories |
| Variable `TARGET_OWNER` | Optional: GitHub-Benutzer oder Organisation; Standard ist der Besitzer dieses Demo-Repositories |

Für eine einfache Demo im persönlichen Account eignet sich ein **classic PAT**
mit `repo` und zusätzlich `workflow`, wenn CI generiert wird. Das Token muss zum
Zielkonto gehören. Für eine Organisation muss das Konto Repositories erstellen
dürfen; gegebenenfalls ist eine SSO-Autorisierung erforderlich. Das Secret wird
nur für die Erstellung und den Push verwendet. Der normale `GITHUB_TOKEN`
verarbeitet Issue-Kommentare und kann keine neuen Repositories außerhalb des
Workflow-Repositories verwalten.

Eine private Demo vermeidet, dass fremde Personen Anfragen stellen. Auch bei einem
öffentlichen Repository prüft die Automation vor jeder Aktion die aktuellen
Schreibrechte des auslösenden Benutzers. Tokens niemals in Issues eintragen.

## Was lässt sich konfigurieren?

| Issue-Feld | Ergebnis |
| --- | --- |
| Aktion: `preview` / `create` | Dateien als Artefakt oder neues Repository |
| Repository-Name | GitHub-Name, README und Gruß der Beispielanwendung |
| Sichtbarkeit: `private` / `public` | Einstellung des neuen GitHub-Repositories |
| Python-Version: 3.11 / 3.12 / 3.13 | Dokumentation und Python-Version in der CI |
| CI aktivieren: `yes` / `no` | Optionaler GitHub-Actions-Testworkflow |

Copier schreibt `.copier-answers.yml` mit den verwendeten Template-Antworten.
Die Sichtbarkeit ist eine GitHub-Einstellung und wird deshalb separat verarbeitet.
Es handelt sich um ein **Copier-Template**, nicht um GitHubs Funktion „Use this
 template“: Copier kann Dateien, Inhalte und Verzeichnisse abhängig von Antworten
rendern. Für die Demo ist daher kein zweites Template-Repository nötig.

## Verhalten bei Fehlern und Wiederholung

Fehler werden als Kommentar gemeldet; das Issue bleibt offen. Nach einer
Korrektur das Issue schließen und erneut öffnen. Änderungen am Issue allein
lösen keine Aktion aus. Nur Titel mit `[repo]` starten den Workflow.

Ein vorhandenes Ziel-Repository wird niemals überschrieben. Eine erneute
`create`-Anfrage mit demselben Namen schlägt fehl. Falls die GitHub-Erstellung
funktioniert, aber der Push scheitert, bleibt das leere Repository bestehen;
der Fehler nennt dessen URL. Es wird nicht automatisch gelöscht. Für den
nächsten Versuch einen anderen Namen wählen oder das leere Repository manuell
bereinigen. Eine neue Vorschau ist jederzeit über ein neues Issue möglich.

## Weitere Aktionen ergänzen

Der Dispatcher befindet sich in `scripts/automation.py`. Eine weitere Aktion,
beispielsweise „Dokumentation erzeugen“, wird als erlaubte Auswahl im Formular
und Parser ergänzt und erhält einen eigenen Handler im Dispatcher. Weitere
Projektoptionen werden im Formular, in der Validierung und in `copier.yml`
definiert. Die Demo akzeptiert bewusst keine frei eingegebenen Template-URLs
oder Shell-Befehle. Das mitgelieferte Template benötigt keine Copier-Tasks.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

Geprüft werden Formularvalidierung, beide CI-Varianten, die Tests des erzeugten
Projekts sowie der Schutz vor Pushes in bestehende oder fremde Repositories.
GitHub-Erstellung und Push werden lokal nicht ausgeführt. Der echte End-to-End-Test
benötigt ein hochgeladenes Demo-Repository und das konfigurierte Secret.

Quellen: [Copier API](https://copier.readthedocs.io/en/stable/reference/api/),
[GitHub-Token und dessen Repository-Grenzen](https://docs.github.com/en/actions/concepts/security/github_token).

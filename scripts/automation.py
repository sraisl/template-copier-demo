"""Issue dispatcher. Only the bundled template and validated options are accepted."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE_FIELDS = {"Aktion", "Repository-Name", "Sichtbarkeit", "CI aktivieren"}
FIELDS = BASE_FIELDS | {"Python-Version", "Vorlage", "Java-Version", "SAST aktivieren", "Sonar konfigurieren", "SONAR_HOST_URL", "Typen", "Reusable Workflow"}

def parse_issue(body):
    parts = re.split(r"^### (.+)\s*$", body, flags=re.MULTILINE)
    fields = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        if label in fields or label not in FIELDS:
            raise ValueError("Unbekanntes oder doppeltes Feld: " + label)
        fields[label] = value.strip()
    if fields.get("Vorlage") == "universal":
        fields.setdefault("CI aktivieren", "yes")
    if not BASE_FIELDS <= set(fields):
        raise ValueError("Bitte das Repository-Issue-Formular vollständig ausfüllen.")
    name = fields["Repository-Name"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
        raise ValueError("Repository-Name: 1–63 Zeichen, Kleinbuchstaben, Zahlen und Bindestriche.")
    fields.setdefault("Vorlage", "python")
    fields.setdefault("SAST aktivieren", "no")
    required_version = {"jdk": "Java-Version", "python": "Python-Version"}.get(fields["Vorlage"])
    if required_version and required_version not in fields:
        raise ValueError("Versionsauswahl fehlt: " + required_version)
    # Older creation issues remain valid, without Sonar configuration.
    fields.setdefault("Sonar konfigurieren", "no")
    fields.setdefault("SONAR_HOST_URL", "")
    for field, choices in {
        "Aktion": {"preview", "create"}, "Sichtbarkeit": {"public", "private"},
        "Vorlage": {"python", "jdk", "universal"}, "CI aktivieren": {"yes", "no"},
        "SAST aktivieren": {"yes", "no"},
        "Sonar konfigurieren": {"yes", "no"},
    }.items():
        if fields[field] not in choices:
            raise ValueError("Ungültige Auswahl: " + field)
    versions = {"Java-Version": {"17", "21", "25"}, "Python-Version": {"3.11", "3.12", "3.13"}}
    if required_version and fields[required_version] not in versions[required_version]:
        raise ValueError("Ungültige Auswahl: " + required_version)
    if fields["Vorlage"] == "universal":
        if fields["CI aktivieren"] != "yes":
            raise ValueError("Das universelle Template erstellt immer den aufrufenden Workflow.")
        fields["Typen"] = parse_types(fields.get("Typen", ""))
        reference = fields.get("Reusable Workflow", "")
        pattern = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+/\.github/workflows/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.ya?ml@[A-Za-z0-9][A-Za-z0-9_./-]*"
        if not re.fullmatch(pattern, reference) or ".." in reference:
            raise ValueError("Reusable Workflow: OWNER/REPO/.github/workflows/DATEI.yml@REF angeben.")
    if fields["SAST aktivieren"] == "yes" and (fields["Vorlage"] != "jdk" or fields["CI aktivieren"] != "yes"):
        raise ValueError("SAST erfordert das JDK-Template und aktivierte CI.")
    if fields["SONAR_HOST_URL"] == "_No response_":
        fields["SONAR_HOST_URL"] = ""
    if fields["Sonar konfigurieren"] == "yes":
        url = fields["SONAR_HOST_URL"]
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"https", "http"} and parsed.hostname
                     and parsed.port != 0 and not parsed.username and not parsed.password
                     and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid or not url.isprintable() or any(c.isspace() for c in url) or len(url) > 2048:
            raise ValueError("SONAR_HOST_URL muss eine HTTP(S)-URL ohne Zugangsdaten, Query oder Fragment sein.")
    return fields


def parse_types(value):
    allowed = {"node", "docker", "spring-boot", "spring-boot-buildpack"}
    if isinstance(value, str):
        try:
            selected = json.loads(value) if value.lstrip().startswith("[") else [item.strip() for item in value.split(",")]
        except json.JSONDecodeError as exc:
            raise ValueError("Typen müssen eine Auswahl oder ein gültiges JSON-Array sein.") from exc
    else:
        selected = value
    if (not isinstance(selected, list) or not selected
            or any(not isinstance(item, str) or item not in allowed for item in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("Mindestens einen erlaubten Typ auswählen; keine unbekannten oder doppelten Typen.")
    return selected


def render(fields, destination):
    if Path(destination).exists():
        raise ValueError("Ausgabeverzeichnis existiert bereits.")
    from copier import run_copy
    template = fields.get("Vorlage", "python")
    if template not in {"python", "jdk", "universal"}:
        raise ValueError("Unbekannte Vorlage.")
    data = {
        "repository_name": fields["Repository-Name"],
        "include_ci": fields["CI aktivieren"] == "yes",
    }
    if template == "jdk":
        data.update(java_version=fields["Java-Version"], include_sast=fields.get("SAST aktivieren") == "yes")
    elif template == "universal":
        data.update(types_json=json.dumps(parse_types(fields["Typen"]), separators=(",", ":")),
                    reusable_workflow=fields["Reusable Workflow"],
                    include_sonar=fields.get("Sonar konfigurieren") == "yes")
    else:
        data["python_version"] = fields["Python-Version"]
    run_copy(str(ROOT / "templates" / template), destination, defaults=True, data=data)



def api(path, token, method="GET", data=None):
    env = {**os.environ, "GH_TOKEN": token}
    command = ["gh", "api", path, "--method", method]
    if data is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                            text=True, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError("GitHub API fehlgeschlagen: " + result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def publish(fields, destination, owner, token, sonar_token=""):
    if fields.get("Sonar konfigurieren") == "yes" and not sonar_token.strip():
        raise ValueError("Factory-Secret SONAR_TOKEN fehlt; es wurde kein Repository erstellt.")
    # Never overwrite or adopt an existing repository. GitHub rejects duplicate names.
    account = api("users/" + owner, token)
    endpoint = "orgs/" + owner + "/repos" if account["type"] == "Organization" else "user/repos"
    if account["type"] != "Organization" and api("user", token)["login"].lower() != owner.lower():
        raise ValueError("Token gehört nicht zum konfigurierten Zielkonto.")
    repo = api(endpoint, token, "POST", {
        "name": fields["Repository-Name"], "private": fields["Sichtbarkeit"] == "private",
        "description": "Mit GitHub Issues und Copier erstellt", "auto_init": False,
    })
    if fields.get("Sonar konfigurieren") == "yes":
        try:
            initialize_sonar(repo["full_name"], fields["SONAR_HOST_URL"], sonar_token, token)
        except RuntimeError as exc:
            raise RuntimeError("Repository erstellt, Sonar-Konfiguration fehlgeschlagen. "
                               "Token-Berechtigungen prüfen und Repository manuell prüfen: "
                               + repo["html_url"]) from exc
    basic = base64.b64encode(("x-access-token:" + token).encode()).decode()
    env = {**os.environ, "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + basic,
           "GIT_TERMINAL_PROMPT": "0"}
    commands = [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "issue-copier-bot"],
        ["git", "config", "user.email", "issue-copier-bot@users.noreply.github.com"],
        ["git", "add", "."], ["git", "commit", "-m", "Initialize project with Copier"],
        ["git", "remote", "add", "origin", repo["clone_url"]],
        ["git", "push", "-u", "origin", "main"],
    ]
    try:
        for command in commands:
            subprocess.run(command, cwd=destination, env=env, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Repository wurde erstellt, Push fehlgeschlagen. "
                           "Das leere Repository manuell prüfen: " + repo["html_url"]) from exc
    return repo["html_url"]



def initialize_sonar(target, host_url, sonar_token, token):
    """Called only after successful creation, before the first push."""
    env = {**os.environ, "GH_TOKEN": token}
    for command, value in [
        (["gh", "variable", "set", "SONAR_HOST_URL", "--repo", target, "--body", host_url], None),
        (["gh", "secret", "set", "SONAR_TOKEN", "--repo", target], sonar_token),
    ]:
        result = subprocess.run(command, input=value, env=env, text=True, capture_output=True)
        if result.returncode:
            # Do not expose subprocess output from operations handling secrets.
            raise RuntimeError("Sonar-Konfiguration fehlgeschlagen. Token-Berechtigungen prüfen.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", type=Path, help="Lokale Vorschau ohne GitHub-Zugriff")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    if args.body:
        fields = parse_issue(args.body.read_text())
        render(fields, args.output)
        print("Lokale Vorschau: " + str(args.output))
        return
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    issue = event["issue"]
    source = os.environ["GITHUB_REPOSITORY"]
    issue_token = os.environ["ISSUE_TOKEN"]
    issue_path = f"repos/{source}/issues/{issue['number']}"
    run_url = f"https://github.com/{source}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    try:
        # Current permissions of the person who triggered this run, including reopening.
        actor = os.environ["GITHUB_ACTOR"]
        permission = api(f"repos/{source}/collaborators/{actor}/permission", issue_token)
        if permission["permission"] not in {"admin", "maintain", "write"}:
            raise ValueError("Nur Personen mit Schreibrechten dürfen Aktionen ausführen.")
        fields = parse_issue(issue["body"] or "")
        owner = os.environ.get("TARGET_OWNER") or source.split('/')[0]
        token = os.environ.get("REPO_FACTORY_TOKEN", "")
        if fields["Aktion"] != "preview" and not token:
            raise ValueError("Repository-Secret REPO_FACTORY_TOKEN fehlt.")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "project"
            render(fields, destination)
            if fields["Aktion"] == "preview":
                import shutil
                if args.output.exists():
                    raise ValueError("Ausgabeverzeichnis existiert bereits.")
                shutil.copytree(destination, args.output)
                message = f"Vorschau erzeugt. Das Artefakt `copier-preview` findest du im [Workflow]({run_url})."
            else:
                url = publish(fields, destination, owner, token, os.environ.get("SONAR_TOKEN", ""))
                message = f"Repository mit Copier erstellt: {url}"
                if fields["Sonar konfigurieren"] == "yes":
                    message += "\n\n`SONAR_HOST_URL` und `SONAR_TOKEN` wurden eingerichtet."
        api(issue_path + "/comments", issue_token, "POST", {"body": message})
        api(issue_path, issue_token, "PATCH", {"state": "closed"})
    except Exception as exc:
        api(issue_path + "/comments", issue_token, "POST", {
            "body": f"Aktion fehlgeschlagen: {exc}\n\n[Workflow-Protokoll]({run_url})"})
        raise


if __name__ == "__main__":
    main()

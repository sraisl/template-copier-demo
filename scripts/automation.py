"""Issue dispatcher. Only the bundled template and validated options are accepted."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CREATE_FIELDS = {"Aktion", "Repository-Name", "Sichtbarkeit", "Python-Version", "CI aktivieren"}
CONFIG_FIELDS = {
    "set-variable": {"Aktion", "Repository-Name", "Variablenname", "Wert"},
    "generate-secret": {"Aktion", "Repository-Name", "Secret-Name"},
}
FIELDS = CREATE_FIELDS | set().union(*CONFIG_FIELDS.values())


def parse_issue(body):
    parts = re.split(r"^### (.+)\s*$", body, flags=re.MULTILINE)
    fields = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        if label in fields or label not in FIELDS:
            raise ValueError("Unbekanntes oder doppeltes Feld: " + label)
        fields[label] = value.strip()
    expected = CONFIG_FIELDS.get(fields.get("Aktion"), CREATE_FIELDS)
    if set(fields) != expected:
        raise ValueError("Bitte das Repository-Issue-Formular vollständig ausfüllen.")
    name = fields["Repository-Name"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
        raise ValueError("Repository-Name: 1–63 Zeichen, Kleinbuchstaben, Zahlen und Bindestriche.")
    if fields["Aktion"] in CONFIG_FIELDS:
        key = "Variablenname" if fields["Aktion"] == "set-variable" else "Secret-Name"
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", fields[key]) or fields[key].startswith("GITHUB_"):
            raise ValueError("Name: maximal 64 Zeichen, A–Z, Zahlen, Unterstrich; kein GITHUB_-Präfix.")
        if key == "Variablenname":
            value = fields["Wert"]
            if not value or len(value) > 256 or not value.isprintable() or value == "_No response_":
                raise ValueError("Variablenwert: 1–256 druckbare Zeichen in einer Zeile.")
        return fields
    for field, choices in {
        "Aktion": {"preview", "create"}, "Sichtbarkeit": {"public", "private"},
        "Python-Version": {"3.11", "3.12", "3.13"}, "CI aktivieren": {"yes", "no"},
    }.items():
        if fields[field] not in choices:
            raise ValueError("Ungültige Auswahl: " + field)
    return fields


def render(fields, destination):
    if Path(destination).exists():
        raise ValueError("Ausgabeverzeichnis existiert bereits.")
    from copier import run_copy
    run_copy(str(ROOT / "templates/python"), destination, defaults=True, data={
        "repository_name": fields["Repository-Name"],
        "python_version": fields["Python-Version"],
        "include_ci": fields["CI aktivieren"] == "yes",
    })


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


def publish(fields, destination, owner, token):
    # Never overwrite or adopt an existing repository. GitHub rejects duplicate names.
    account = api("users/" + owner, token)
    endpoint = "orgs/" + owner + "/repos" if account["type"] == "Organization" else "user/repos"
    if account["type"] != "Organization" and api("user", token)["login"].lower() != owner.lower():
        raise ValueError("Token gehört nicht zum konfigurierten Zielkonto.")
    repo = api(endpoint, token, "POST", {
        "name": fields["Repository-Name"], "private": fields["Sichtbarkeit"] == "private",
        "description": "Mit GitHub Issues und Copier erstellt", "auto_init": False,
    })
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



def configure_repository(fields, source, owner, actor, token):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner):
        raise ValueError("Ungültiger TARGET_OWNER.")
    target = owner + "/" + fields["Repository-Name"]
    if target.lower() == source.lower():
        raise ValueError("Das Factory-Repository darf nicht als Ziel konfiguriert werden.")
    # Write access to the factory alone must not grant access to unrelated targets.
    permission = api(f"repos/{target}/collaborators/{actor}/permission", token)
    if permission["permission"] not in {"admin", "maintain", "write"}:
        raise ValueError("Für diese Aktion sind Schreibrechte im Ziel-Repository erforderlich.")
    env = {**os.environ, "GH_TOKEN": token}
    if fields["Aktion"] == "set-variable":
        name = fields["Variablenname"]
        command = ["gh", "variable", "set", name, "--repo", target, "--body", fields["Wert"]]
        value = None
        message = f"Variable `{name}` in `{target}` gesetzt."
    else:
        name = fields["Secret-Name"]
        # Metadata only: secret values cannot be read from GitHub.
        result = subprocess.run(["gh", "secret", "list", "--repo", target, "--json", "name"],
                                env=env, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError("Secret-Namen konnten nicht geprüft werden. Token-Berechtigungen prüfen.")
        if any(item["name"].upper() == name for item in json.loads(result.stdout)):
            raise ValueError("Secret existiert bereits; es wird nicht automatisch rotiert.")
        value = secrets.token_urlsafe(32)
        command = ["gh", "secret", "set", name, "--repo", target]
        message = f"Zufälliges Demo-Secret `{name}` in `{target}` erstellt. Der Wert wird nicht ausgegeben."
    result = subprocess.run(command, input=value, env=env, text=True, capture_output=True)
    if result.returncode:
        # Never forward CLI output from a secret-writing operation into issues or logs.
        raise RuntimeError("Konfiguration fehlgeschlagen. Token-Berechtigungen im Ziel-Repository prüfen.")
    return message + f"\n\n[Repository-Einstellungen](https://github.com/{target}/settings/secrets/actions)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", type=Path, help="Lokale Vorschau ohne GitHub-Zugriff")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    if args.body:
        fields = parse_issue(args.body.read_text())
        if fields["Aktion"] in CONFIG_FIELDS:
            raise ValueError("--body unterstützt nur lokale Projektvorschauen.")
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
        if fields["Aktion"] in CONFIG_FIELDS:
            message = configure_repository(fields, source, owner, actor, token)
        else:
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
                    url = publish(fields, destination, owner, token)
                    message = f"Repository mit Copier erstellt: {url}"
        api(issue_path + "/comments", issue_token, "POST", {"body": message})
        api(issue_path, issue_token, "PATCH", {"state": "closed"})
    except Exception as exc:
        api(issue_path + "/comments", issue_token, "POST", {
            "body": f"Aktion fehlgeschlagen: {exc}\n\n[Workflow-Protokoll]({run_url})"})
        raise


if __name__ == "__main__":
    main()

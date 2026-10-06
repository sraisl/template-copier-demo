import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("automation", ROOT / "scripts/automation.py")
automation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(automation)
BODY = (ROOT / "examples/preview.md").read_text()


class AutomationTests(unittest.TestCase):
    def test_valid_form(self):
        self.assertEqual(automation.parse_issue(BODY)["Repository-Name"], "demo-service")

    def test_rejects_missing_duplicate_and_injected_values(self):
        for body in [BODY.replace("### Aktion", "### Unknown"),
                     BODY + "\n### Aktion\npreview\n",
                     BODY.replace("demo-service", "../../escape"),
                     BODY.replace("demo-service", 'bad"; echo x'),
                     BODY.replace("private", "internal"),
                     BODY.replace("3.13", "3.99")]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                automation.parse_issue(body)

    def test_render_with_and_without_ci(self):
        for ci in ["yes", "no"]:
            with self.subTest(ci=ci), tempfile.TemporaryDirectory() as temp:
                fields = automation.parse_issue(BODY)
                fields["CI aktivieren"] = ci
                destination = Path(temp) / "project"
                automation.render(fields, destination)
                self.assertEqual((destination / ".github/workflows/ci.yml").exists(), ci == "yes")
                self.assertTrue((destination / ".copier-answers.yml").exists())
                subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                               cwd=destination, check=True, capture_output=True)

    def test_unauthorized_actor_cannot_render_or_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            event = Path(temp) / "event.json"
            event.write_text(json.dumps({"issue": {"number": 1, "body": BODY}}))
            with patch.dict(os.environ, {
                "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "demo/factory",
                "GITHUB_ACTOR": "visitor", "GITHUB_RUN_ID": "123", "ISSUE_TOKEN": "fake",
            }), patch.object(sys, "argv", ["automation.py"]), patch.object(
                automation, "api", side_effect=[{"permission": "read"}, {}]
            ) as api, patch.object(automation, "render") as render, patch.object(
                automation, "publish"
            ) as publish:
                with self.assertRaises(ValueError):
                    automation.main()
                render.assert_not_called()
                publish.assert_not_called()
                self.assertIn("fehlgeschlagen", api.call_args.args[3]["body"])

    def test_existing_repository_never_gets_pushed(self):
        fields = automation.parse_issue(BODY)
        with patch.object(automation, "api", side_effect=[
            {"type": "Organization"}, RuntimeError("already exists")
        ]), patch.object(automation.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                automation.publish(fields, Path("unused"), "demo-org", "fake-token")
            run.assert_not_called()

    def test_personal_owner_must_match_token(self):
        with patch.object(automation, "api", side_effect=[
            {"type": "User"}, {"login": "someone-else"}
        ]), self.assertRaises(ValueError):
            automation.publish(automation.parse_issue(BODY), Path("unused"), "demo-user", "fake-token")


if __name__ == "__main__":
    unittest.main()

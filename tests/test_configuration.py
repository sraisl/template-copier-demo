import json
import os
import sys
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from test_automation import automation, ROOT

VARIABLE = (ROOT / 'examples/set-variable.md').read_text()
SECRET = (ROOT / 'examples/generate-secret.md').read_text()


class ConfigurationTests(unittest.TestCase):
    def test_forms_and_invalid_input(self):
        self.assertEqual(automation.parse_issue(VARIABLE)['Aktion'], 'set-variable')
        self.assertEqual(automation.parse_issue(SECRET)['Secret-Name'], 'DEMO_TOKEN')
        for body in [VARIABLE.replace('APP_ENV', 'GITHUB_TOKEN'),
                     SECRET.replace('DEMO_TOKEN', 'bad-name'),
                     VARIABLE.replace('\ndemo\n', '\nline1\nline2\n'),
                     VARIABLE + '\n### Secret-Name\nTOKEN\n',
                     VARIABLE.replace('demo-service', 'someone/repo')]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                automation.parse_issue(body)

    def test_configuration_dispatch_closes_issue_without_rendering(self):
        with tempfile.TemporaryDirectory() as temp:
            event = Path(temp) / 'event.json'
            event.write_text(json.dumps({'issue': {'number': 2, 'body': VARIABLE}}))
            with patch.dict(os.environ, {
                'GITHUB_EVENT_PATH': str(event), 'GITHUB_REPOSITORY': 'owner/factory',
                'GITHUB_ACTOR': 'actor', 'GITHUB_RUN_ID': '123', 'ISSUE_TOKEN': 'fake',
                'REPO_FACTORY_TOKEN': 'fake-factory', 'TARGET_OWNER': 'owner',
            }), patch.object(sys, 'argv', ['automation.py']), patch.object(
                automation, 'api', side_effect=[{'permission': 'write'}, {}, {}]
            ) as api, patch.object(automation, 'configure_repository', return_value='Variable gesetzt.') as configure, patch.object(
                automation, 'render'
            ) as render:
                automation.main()
                configure.assert_called_once()
                render.assert_not_called()
                self.assertEqual(api.call_args.args[3], {'state': 'closed'})

    def test_variable_set(self):
        with patch.object(automation, 'api', return_value={'permission': 'write'}), patch.object(
            automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            message = automation.configure_repository(automation.parse_issue(VARIABLE),
                                                       'owner/factory', 'owner', 'actor', 'fake')
            self.assertIn('APP_ENV', message)
            self.assertEqual(run.call_args.args[0], [
                'gh', 'variable', 'set', 'APP_ENV', '--repo', 'owner/demo-service', '--body', 'demo'])

    def test_denies_factory_and_target_without_write_access(self):
        for source, permission in [('owner/demo-service', 'write'), ('owner/factory', 'read')]:
            with patch.object(automation, 'api', return_value={'permission': permission}), patch.object(
                automation.subprocess, 'run'
            ) as run, self.assertRaises(ValueError):
                automation.configure_repository(automation.parse_issue(VARIABLE), source, 'owner', 'actor', 'fake')
            run.assert_not_called()

    def test_secret_is_stdin_only_and_not_in_result(self):
        with patch.object(automation, 'api', return_value={'permission': 'write'}), patch.object(
            automation.secrets, 'token_urlsafe', return_value='never-display-this'
        ) as generate, patch.object(automation.subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 0, '[]'), subprocess.CompletedProcess([], 0, '')
        ]) as run:
            message = automation.configure_repository(automation.parse_issue(SECRET),
                                                       'owner/factory', 'owner', 'actor', 'fake')
            generate.assert_called_once_with(32)
            self.assertEqual(run.call_args.kwargs['input'], 'never-display-this')
            self.assertNotIn('never-display-this', str(run.call_args.args))
            self.assertNotIn('never-display-this', message)

    def test_existing_secret_is_not_rotated(self):
        with patch.object(automation, 'api', return_value={'permission': 'write'}), patch.object(
            automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[{"name":"DEMO_TOKEN"}]')
        ) as run, patch.object(automation.secrets, 'token_urlsafe') as generate:
            with self.assertRaises(ValueError):
                automation.configure_repository(automation.parse_issue(SECRET),
                                                'owner/factory', 'owner', 'actor', 'fake')
            self.assertEqual(run.call_count, 1)
            generate.assert_not_called()

    def test_failed_secret_write_does_not_expose_cli_output(self):
        with patch.object(automation, 'api', return_value={'permission': 'write'}), patch.object(
            automation.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, '[]'),
                subprocess.CompletedProcess([], 1, 'sensitive-output', 'sensitive-error')]
        ):
            with self.assertRaises(RuntimeError) as exc:
                automation.configure_repository(automation.parse_issue(SECRET),
                                                'owner/factory', 'owner', 'actor', 'fake')
            self.assertNotIn('sensitive', str(exc.exception))


if __name__ == '__main__':
    unittest.main()

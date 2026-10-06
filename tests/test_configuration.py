import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from test_automation import automation, ROOT

SONAR_BODY = (ROOT / 'examples/create-with-sonar.md').read_text()
REPO = {'full_name': 'owner/demo-sonar-service', 'html_url': 'https://github.com/owner/demo-sonar-service',
        'clone_url': 'https://github.com/owner/demo-sonar-service.git'}


class SonarCreationTests(unittest.TestCase):
    def test_validates_url_and_rejects_old_configuration_actions(self):
        self.assertEqual(automation.parse_issue(SONAR_BODY)['SONAR_HOST_URL'], 'https://sonarqube.example.com')
        for url in ['', 'file:///tmp/demo', 'https://user:token@example.com',
                    'https://host/?token=secret', 'https://host/#fragment',
                    'https://host:invalid', 'https://host/white space']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                automation.parse_issue(SONAR_BODY.replace('https://sonarqube.example.com', url))
        for action in ['set-variable', 'generate-secret']:
            with self.assertRaises(ValueError):
                automation.parse_issue(SONAR_BODY.replace('\ncreate\n', '\n' + action + '\n'))

    def test_missing_sonar_token_fails_before_creating_repository(self):
        with patch.object(automation, 'api') as api, self.assertRaises(ValueError):
            automation.publish(automation.parse_issue(SONAR_BODY), Path('unused'), 'owner', 'fake')
        api.assert_not_called()

    def test_existing_repository_is_not_configured(self):
        with patch.object(automation, 'api', side_effect=[{'type': 'Organization'}, RuntimeError('exists')]), patch.object(
            automation, 'initialize_sonar'
        ) as configure, self.assertRaises(RuntimeError):
            automation.publish(automation.parse_issue(SONAR_BODY), Path('unused'), 'owner', 'fake', 'sonar-value')
        configure.assert_not_called()

    def test_sonar_is_configured_after_creation_before_push(self):
        events = []
        def api(path, *args):
            if path.startswith('users/'):
                return {'type': 'Organization'}
            events.append('create')
            return REPO
        def configure(*args):
            events.append('configure')
        def run(command, **kwargs):
            if command[:2] == ['git', 'push']:
                events.append('push')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(automation, 'api', side_effect=api), patch.object(
            automation, 'initialize_sonar', side_effect=configure
        ) as initialize, patch.object(automation.subprocess, 'run', side_effect=run):
            automation.publish(automation.parse_issue(SONAR_BODY), Path('unused'), 'owner', 'fake', 'sonar-value')
            initialize.assert_called_once_with(REPO['full_name'], 'https://sonarqube.example.com', 'sonar-value', 'fake')
        self.assertEqual(events, ['create', 'configure', 'push'])

    def test_token_is_stdin_only(self):
        with patch.object(automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            automation.initialize_sonar(REPO['full_name'], 'https://sonar.example.com', 'private-sonar-token', 'fake')
            self.assertEqual(run.call_args.kwargs['input'], 'private-sonar-token')
            self.assertNotIn('private-sonar-token', str(run.call_args.args))
            self.assertEqual(run.call_args.args[0][:4], ['gh', 'secret', 'set', 'SONAR_TOKEN'])
            self.assertEqual(run.call_args_list[0].args[0][:4], ['gh', 'variable', 'set', 'SONAR_HOST_URL'])

    def test_configuration_failure_mentions_repo_without_cli_secret_output(self):
        with patch.object(automation, 'api', side_effect=[{'type': 'Organization'}, REPO]), patch.object(
            automation.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0),
                subprocess.CompletedProcess([], 1, 'private-sonar-token', 'private-sonar-token')]
        ) as run:
            with self.assertRaises(RuntimeError) as exc:
                automation.publish(automation.parse_issue(SONAR_BODY), Path('unused'), 'owner', 'fake', 'private-sonar-token')
            self.assertIn(REPO['html_url'], str(exc.exception))
            self.assertNotIn('private-sonar-token', str(exc.exception))
            self.assertEqual(run.call_count, 2)  # No git push following failed configuration.

    def test_disabled_sonar_does_not_require_token_or_configure_repository(self):
        fields = automation.parse_issue(SONAR_BODY.replace('\nyes\n\n### SONAR_HOST_URL', '\nno\n\n### SONAR_HOST_URL'))
        with patch.object(automation, 'api', side_effect=[{'type': 'Organization'}, REPO]), patch.object(
            automation, 'initialize_sonar'
        ) as configure, patch.object(automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            automation.publish(fields, Path('unused'), 'owner', 'fake')
        configure.assert_not_called()


if __name__ == '__main__':
    unittest.main()

import itertools
import json
from pathlib import Path
import tempfile
import subprocess
from unittest.mock import patch
import unittest
import yaml

from test_automation import automation, ROOT

BODY = (ROOT / 'examples/preview-universal.md').read_text()
TYPES = ['node', 'docker', 'spring-boot', 'spring-boot-buildpack']
REFERENCE = 'sraisl/reusable-workflows/.github/workflows/ci.yml@main'


class UniversalTemplateTests(unittest.TestCase):
    def test_all_nonempty_combinations_create_only_the_caller(self):
        for count in range(1, len(TYPES) + 1):
            for selection in itertools.combinations(TYPES, count):
                with self.subTest(selection=selection), tempfile.TemporaryDirectory() as temp:
                    fields = automation.parse_issue(BODY.replace(', '.join(TYPES), ', '.join(selection)))
                    destination = Path(temp) / 'project'
                    automation.render(fields, destination)
                    files = [p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()]
                    self.assertEqual(files, ['.github/workflows/ci.yml'])
                    workflow = yaml.safe_load((destination / files[0]).read_text())
                    self.assertEqual(set(workflow['jobs']), {'ci'})
                    caller = workflow['jobs']['ci']
                    self.assertEqual(set(caller), {'uses', 'with'})
                    self.assertEqual(caller['uses'], REFERENCE)
                    self.assertIsInstance(caller['with']['types'], str)
                    self.assertEqual(json.loads(caller['with']['types']), list(selection))

    def test_sonar_is_configured_on_creation_and_token_is_forwarded(self):
        fields = automation.parse_issue((ROOT / 'examples/create-universal-with-sonar.md').read_text())
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'project'
            automation.render(fields, destination)
            files = [p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()]
            self.assertEqual(files, ['.github/workflows/ci.yml'])
            workflow = yaml.safe_load((destination / files[0]).read_text())
            self.assertEqual(workflow['jobs']['ci']['secrets'], {'SONAR_TOKEN': '${{ secrets.SONAR_TOKEN }}'})
            self.assertEqual(set(workflow['jobs']['ci']['with']), {'types'})
            repo = {'full_name': 'owner/demo-universal-service',
                    'html_url': 'https://github.com/owner/demo-universal-service',
                    'clone_url': 'https://github.com/owner/demo-universal-service.git'}
            with patch.object(automation, 'api', side_effect=[{'type': 'Organization'}, repo, None]), patch.object(
                automation, 'initialize_sonar'
            ) as initialize, patch.object(automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                automation.publish(fields, destination, 'owner', 'fake', 'private-sonar-token')
                initialize.assert_called_once_with(repo['full_name'], 'https://sonarqube.example.com', 'private-sonar-token', 'fake')
            self.assertNotIn('private-sonar-token', (destination / files[0]).read_text())

    def test_universal_missing_sonar_token_prevents_creation(self):
        fields = automation.parse_issue((ROOT / 'examples/create-universal-with-sonar.md').read_text())
        with patch.object(automation, 'api') as api, self.assertRaises(ValueError):
            automation.publish(fields, Path('unused'), 'owner', 'fake')
        api.assert_not_called()

    def test_jdk_home_selection_is_validated_and_published(self):
        repo = {'full_name': 'owner/demo-universal-service',
                'html_url': 'https://github.com/owner/demo-universal-service',
                'clone_url': 'https://github.com/owner/demo-universal-service.git'}
        for value in ['/opt/jdk-21', '/opt/jdk-25', '/opt/jdk-17']:
            with self.subTest(value=value):
                fields = automation.parse_issue(BODY.replace('/opt/jdk-21', value))
                with patch.object(automation, 'api', side_effect=[{'type': 'Organization'}, repo, None]) as api, patch.object(
                    automation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)
                ):
                    automation.publish(fields, Path('unused'), 'owner', 'fake')
                self.assertEqual(api.call_args.args, (
                    'repos/owner/demo-universal-service/actions/variables', 'fake', 'POST',
                    {'name': 'JDK_HOME', 'value': value}))
        with self.assertRaises(ValueError):
            automation.parse_issue(BODY.replace('/opt/jdk-21', '/opt/jdk-99'))
        legacy = BODY.split('### JDK_HOME')[0]
        self.assertEqual(automation.parse_issue(legacy)['JDK_HOME'], '/opt/jdk-21')

    def test_jdk_home_configuration_failure_prevents_push(self):
        fields = automation.parse_issue(BODY)
        repo = {'full_name': 'owner/demo', 'html_url': 'https://github.com/owner/demo'}
        with patch.object(automation, 'api', side_effect=[
            {'type': 'Organization'}, repo, RuntimeError('permission denied')
        ]), patch.object(automation.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'JDK_HOME-Konfiguration fehlgeschlagen'):
                automation.publish(fields, Path('unused'), 'owner', 'fake')
            run.assert_not_called()

    def test_json_input_is_supported(self):
        fields = automation.parse_issue(BODY.replace(', '.join(TYPES), '["node", "docker"]'))
        self.assertEqual(fields['Typen'], ['node', 'docker'])

    def test_invalid_types_are_rejected(self):
        for value in ['', 'unknown', 'node, node', 'node,', '_No response_', '[]',
                      '["node", "unknown"]', '[true]', '[{}]', '["node",', 'node\nrun: attack']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                automation.parse_issue(BODY.replace(', '.join(TYPES), value))

    def test_external_workflow_reference_is_required_and_validated(self):
        for value in ['', './.github/workflows/ci.yml', 'owner/repo/.github/workflows/ci.yml',
                      'owner/repo/.github/workflows/../ci.yml@main',
                      'owner/repo/.github/workflows/ci.yml@main\n    secrets: inherit',
                      "owner/repo/.github/workflows/ci.yml@main'"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                automation.parse_issue(BODY.replace(REFERENCE, value))
        for ref in ['v1', 'feature/ci', 'a' * 40]:
            fields = automation.parse_issue(BODY.replace('@main', '@' + ref))
            self.assertTrue(fields['Reusable Workflow'].endswith('@' + ref))

    def test_universal_requires_the_calling_workflow(self):
        with self.assertRaises(ValueError):
            automation.parse_issue(BODY + '\n### CI aktivieren\n\nno\n')


if __name__ == '__main__':
    unittest.main()

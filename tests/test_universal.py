import itertools
import json
from pathlib import Path
import tempfile
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

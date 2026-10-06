from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import yaml

from test_automation import automation, ROOT

BODY = (ROOT / 'examples/preview-jdk.md').read_text()


class JdkTemplateTests(unittest.TestCase):
    def test_form_validation(self):
        self.assertEqual(automation.parse_issue(BODY)['Vorlage'], 'jdk')
        for body in [BODY.replace('\n21\n', '\n99\n'),
                     BODY.replace('\njdk\n', '\n../../escape\n'),
                     BODY.replace('### Java-Version', '### Python-Version'),
                     BODY.replace('### CI aktivieren\n\nyes', '### CI aktivieren\n\nno')]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                automation.parse_issue(body)

    def test_java_versions_and_optional_sast_job(self):
        for version in ['17', '21', '25']:
            for sast in ['yes', 'no']:
                with self.subTest(version=version, sast=sast), tempfile.TemporaryDirectory() as temp:
                    fields = automation.parse_issue(BODY)
                    fields.update({'Java-Version': version, 'SAST aktivieren': sast})
                    destination = Path(temp) / 'project'
                    automation.render(fields, destination)
                    self.assertFalse((destination / 'main.py').exists())
                    pom = ET.parse(destination / 'pom.xml')
                    release = pom.find('.//{*}maven.compiler.release')
                    self.assertEqual(release.text, version)
                    workflow = yaml.safe_load((destination / '.github/workflows/ci.yml').read_text())
                    self.assertEqual('sast' in workflow['jobs'], sast == 'yes')
                    for job in workflow['jobs'].values():
                        steps = job['steps']
                        self.assertEqual(steps[0]['uses'], 'actions/checkout@v4')
                        setup = next(step for step in steps if step.get('uses', '').startswith('actions/setup-java@'))
                        self.assertEqual(setup['with']['java-version'], version)
                    if sast == 'yes':
                        scan = workflow['jobs']['sast']['steps'][-1]
                        self.assertTrue(scan['uses'].startswith('sraisl/polyscan-action@'))
                        self.assertEqual(scan['with']['engines'], 'spotbugs')
                    self.assertTrue((destination / 'src/test/java/demo/AppTest.java').exists())
                    self.assertTrue((destination / '.copier-answers.yml').exists())

    def test_no_ci_creates_no_workflows(self):
        fields = automation.parse_issue(BODY.replace('### CI aktivieren\n\nyes', '### CI aktivieren\n\nno')
                                        .replace('### SAST aktivieren\n\nyes', '### SAST aktivieren\n\nno'))
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'project'
            automation.render(fields, destination)
            self.assertFalse((destination / '.github').exists())
            self.assertTrue((destination / 'pom.xml').exists())

    @unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK not installed')
    def test_generated_application_compiles_and_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'project'
            automation.render(automation.parse_issue(BODY), destination)
            classes = Path(temp) / 'classes'
            classes.mkdir()
            # Java 17 baseline runs on the JDKs available on developer machines and CI.
            subprocess.run(['javac', '--release', '17', '-d', str(classes),
                            str(destination / 'src/main/java/demo/App.java')], check=True, capture_output=True)
            result = subprocess.run(['java', '-cp', str(classes), 'demo.App'],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'Hallo von demo-java-service!')


if __name__ == '__main__':
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
class RequirementTests(unittest.TestCase):
    def test_real_cli_flags_hidden_input_only_and_does_not_echo_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'SKILL.md').write_text('---\nname: sample\ndescription: test\n---\n# sample\n')
            (root/'scripts').mkdir();(root/'scripts/setup.py').write_text('api_key = getpass("TEST_ONLY_DO_NOT_ECHO")')
            script=Path(__file__).parents[1]/'scripts/review_requirements.py'
            p=subprocess.run([sys.executable,str(script),str(root)],capture_output=True,text=True,check=True)
            data=json.loads(p.stdout)
            self.assertEqual(data['status'],'needs-review')
            self.assertTrue(data['signals']['credentials'])
            self.assertFalse(data['credential_component']['present'])
            self.assertNotIn('TEST_ONLY_DO_NOT_ECHO',p.stdout)

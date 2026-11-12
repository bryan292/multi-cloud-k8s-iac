"""DOC-002: execute explicitly marked offline documentation commands."""
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_offline_commands(self):
        count = 0
        for path in (ROOT / 'docs').glob('*.md'):
            for block in re.findall(r'```sh offline\n(.*?)```', path.read_text(), re.S):
                for line in block.splitlines():
                    if not line.strip() or line.lstrip().startswith('#'):
                        continue
                    args = shlex.split(line)
                    self.assertEqual(args[0], 'python3')
                    self.assertIn(args[1], ('scripts/iac.py', 'scripts/preflight.py'))
                    self.assertTrue('--help' in args or (args[1] == 'scripts/preflight.py' and '--offline' in args))
                    args[0] = sys.executable
                    with self.subTest(document=path.name, command=line):
                        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    count += 1
        self.assertGreaterEqual(count, 5)

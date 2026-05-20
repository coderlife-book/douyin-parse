import os
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT_DIR / "start.sh"


class StartScriptTests(unittest.TestCase):
    def test_start_script_bootstraps_web_service(self):
        self.assertTrue(START_SCRIPT.exists())
        self.assertTrue(os.access(START_SCRIPT, os.X_OK))

        content = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("PYTHON_BIN", content)
        self.assertIn("start.py", content)


if __name__ == "__main__":
    unittest.main()

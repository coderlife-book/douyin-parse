import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_INDEX = ROOT_DIR / "web" / "index.html"


class ElementCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class WebTranscriptionUiTests(unittest.TestCase):
    def setUp(self):
        self.html = WEB_INDEX.read_text(encoding="utf-8")
        parser = ElementCollector()
        parser.feed(self.html)
        self.elements = parser.elements

    def find_by_id(self, element_id):
        for tag, attrs in self.elements:
            if attrs.get("id") == element_id:
                return tag, attrs
        self.fail(f"页面缺少 #{element_id}")

    def test_page_exposes_two_accessible_business_tabs(self):
        tablists = [attrs for _, attrs in self.elements if attrs.get("role") == "tablist"]
        tabs = [attrs for _, attrs in self.elements if attrs.get("role") == "tab"]

        self.assertEqual(len(tablists), 1)
        self.assertEqual(
            [(item.get("data-tab"), item.get("aria-selected")) for item in tabs],
            [("download", "true"), ("transcription", "false")],
        )
        self.assertEqual(self.find_by_id("downloadTab")[1]["role"], "tabpanel")
        self.assertEqual(self.find_by_id("transcriptionTab")[1]["role"], "tabpanel")

    def test_transcription_panel_has_labeled_input_progress_and_result_actions(self):
        labels = [attrs for tag, attrs in self.elements if tag == "label"]

        self.assertTrue(any(attrs.get("for") == "transcriptionUrl" for attrs in labels))
        self.assertTrue(any(attrs.get("for") == "transcriptionModel" for attrs in labels))
        self.assertEqual(self.find_by_id("transcriptionModel")[0], "select")
        self.assertEqual(self.find_by_id("transcriptionStatus")[1]["aria-live"], "polite")
        self.find_by_id("transcriptionProgressFill")
        _, result_attrs = self.find_by_id("transcriptResult")
        self.assertNotIn("hidden", result_attrs)
        self.find_by_id("transcriptText")
        self.find_by_id("transcriptSegments")
        self.find_by_id("copyTranscriptBtn")
        self.find_by_id("downloadTranscriptBtn")
        self.find_by_id("transcriptionTaskList")

    def test_inline_javascript_is_valid(self):
        match = re.search(r"<script>([\s\S]*?)</script>", self.html)
        self.assertIsNotNone(match)

        result = subprocess.run(
            ["node", "-e", "new Function(process.argv[1])", match.group(1)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

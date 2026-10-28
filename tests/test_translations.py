"""Flow descriptions receive placeholders; dialog titles must remain self-contained."""

import json
import re
import unittest
from pathlib import Path


class DialogTranslationTests(unittest.TestCase):
    def test_titles_have_no_unprovided_format_variables(self):
        root = Path(__file__).parents[1] / "custom_components/solarshare"
        paths = [root / "strings.json", *sorted((root / "translations").glob("*.json"))]
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("config", "options"):
                for step, text in data[section]["step"].items():
                    with self.subTest(path=path.name, section=section, step=step):
                        self.assertEqual(re.findall(r"\{[^{}]+\}", text.get("title", "")), [])

    def test_descriptions_keep_installation_name_and_inverter_count(self):
        root = Path(__file__).parents[1] / "custom_components/solarshare"
        for path in (root / "translations").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("config", "options"):
                self.assertIn("{name}", data[section]["step"]["site_menu"]["description"])
                self.assertIn("{count}", data[section]["step"]["inverters"]["description"])

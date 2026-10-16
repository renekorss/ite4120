"""Fast repository checks; relational behavior is verified on PostgreSQL."""
from pathlib import Path
import unittest
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class ArtifactTests(unittest.TestCase):
    def test_changelog_references_and_rollbacks_exist(self):
        tree = ET.parse(ROOT / "database/changelog/db.changelog.xml")
        ns = {"lb": "http://www.liquibase.org/xml/ns/dbchangelog"}
        identifiers = []
        for change in tree.findall("lb:changeSet", ns):
            identifiers.append((change.attrib["id"], change.attrib["author"]))
            self.assertIsNotNone(change.find("lb:rollback", ns))
            for sql_file in change.findall(".//lb:sqlFile", ns):
                path = ROOT / "database/changelog" / sql_file.attrib["path"]
                self.assertTrue(path.is_file(), str(path))
                self.assertTrue(path.read_text().strip(), str(path))
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_story_traceability_is_complete(self):
        stories = (ROOT / "user-stories.md").read_text()
        mapping = (ROOT / "docs/database.md").read_text()
        import re
        for story in re.findall(r"### (US-\d+):", stories):
            self.assertIn(f"| {story} |", mapping)

    def test_shell_syntax(self):
        for directory in ("database", "scripts"):
            for path in (ROOT / directory).glob("*.sh"):
                subprocess.run(["sh", "-n", str(path)], check=True)

    def test_text_hygiene(self):
        paths = [ROOT / "README.md", ROOT / "compose.yaml", ROOT / ".env.example"]
        for directory in ("database", "scripts", "docs"):
            paths.extend(p for p in (ROOT / directory).rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts)
        for path in paths:
            text = path.read_text()
            self.assertTrue(text.endswith("\n"), str(path))
            for number, line in enumerate(text.splitlines(), 1):
                self.assertEqual(line, line.rstrip(), f"{path}:{number}")


if __name__ == "__main__":
    unittest.main()

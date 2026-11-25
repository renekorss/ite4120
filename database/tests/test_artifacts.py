"""Fast repository checks; relational behavior is verified on PostgreSQL."""
from pathlib import Path
import json
import re
import unittest
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class ArtifactTests(unittest.TestCase):
    def test_frontend_collection_matches_api_sections_and_authentication(self):
        collection = json.loads((ROOT / "postman/frontend-api.postman_collection.json").read_text())
        spec = json.loads((ROOT / "api/openapi.json").read_text())
        expected_tags = {operation["tags"][0]
                         for methods in spec["paths"].values() for operation in methods.values()}
        self.assertEqual({folder["name"] for folder in collection["item"]}, expected_tags)
        self.assertEqual(collection["auth"]["type"], "bearer")
        self.assertEqual(collection["auth"]["bearer"][0]["value"], "{{accessToken}}")
        covered = set()
        names = []
        for folder in collection["item"]:
            for item in folder["item"]:
                names.append(item["name"])
                request = item["request"]
                path = request["url"].removeprefix("{{apiBaseUrl}}").split("?")[0]
                method = request["method"].lower()
                matches = [route for route, methods in spec["paths"].items()
                           if method in methods and re.fullmatch(
                               re.sub(r"\{[^}]+\}", "[^/]+", route), path)]
                self.assertEqual(len(matches), 1, item["name"])
                route = matches[0]
                operation = spec["paths"][route][method]
                self.assertEqual(folder["name"], operation["tags"][0])
                if operation.get("security"):
                    # Explicit noauth is used only for the unauthenticated negative test.
                    if request.get("auth"):
                        self.assertEqual(item["name"], "03 Protected profile requires authentication")
                else:
                    self.assertEqual(request["auth"]["type"], "noauth")
                covered.add((route, method))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(covered, {(route, method) for route, methods in spec["paths"].items()
                                   for method in methods})
        self.assertEqual(next(v["value"] for v in collection["variable"]
                              if v["key"] == "accessToken"), "")

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

    def test_acceptance_audit_covers_each_criterion(self):
        stories = (ROOT / "user-stories.md").read_text()
        audit = (ROOT / "docs/acceptance.md").read_text()
        sections = re.split(r"^### (US-\d+):", stories, flags=re.MULTILINE)
        for story, section in zip(sections[1::2], sections[2::2]):
            criteria = re.findall(r"^- ", section, re.MULTILINE)
            rows = [line for line in audit.splitlines() if line.startswith(f"| {story} |")]
            self.assertEqual(len(rows), 1, story)
            self.assertEqual(re.findall(r"\bAC(\d+)\.", rows[0].split("|")[2]),
                             [str(i + 1) for i in range(len(criteria))], story)

    def test_shell_syntax(self):
        for directory in ("database", "scripts"):
            for path in (ROOT / directory).glob("*.sh"):
                subprocess.run(["sh", "-n", str(path)], check=True)

    def test_text_hygiene(self):
        paths = [ROOT / "README.md", ROOT / "compose.yaml", ROOT / "compose.mock.yaml", ROOT / ".env.example"]
        for directory in ("database", "scripts", "docs", "mocks"):
            paths.extend(p for p in (ROOT / directory).rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts
                         and p.name != ".DS_Store")
        for path in paths:
            text = path.read_text()
            self.assertTrue(text.endswith("\n"), str(path))
            for number, line in enumerate(text.splitlines(), 1):
                self.assertEqual(line, line.rstrip(), f"{path}:{number}")


if __name__ == "__main__":
    unittest.main()

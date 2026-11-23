import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_extension import build


class BuildExtensionTest(unittest.TestCase):
    def setUp(self):
        self.zip_path = build(Path(tempfile.mkdtemp()))
        self.names = set(zipfile.ZipFile(self.zip_path).namelist())
        self.manifest = json.loads(zipfile.ZipFile(self.zip_path).read("manifest.json"))

    def test_zip_is_named_after_manifest_version(self):
        self.assertEqual(self.zip_path.name, f"ffmenu-kt-{self.manifest['version']}.zip")

    def test_every_file_the_manifest_names_is_in_the_zip(self):
        m = self.manifest
        referenced = {m["background"]["service_worker"], *m["background"]["scripts"], m["options_ui"]["page"],
                      *m["icons"].values(), *m["action"]["default_icon"].values(),
                      *(f for script in m["content_scripts"] for f in script["js"] + script["css"])}

        self.assertEqual(referenced - self.names, set())

    def test_store_requires_a_128_px_icon(self):
        self.assertIn("128", self.manifest["icons"])


if __name__ == "__main__":
    unittest.main()

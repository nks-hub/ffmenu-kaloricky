import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

MD5_JS = Path(__file__).resolve().parent.parent / "extension" / "md5.js"
RUNNER = """
const vm = require("vm"), fs = require("fs");
const context = { TextEncoder };
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
const inputs = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(inputs.map((s) => context.md5(s))));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ExtensionMd5Test(unittest.TestCase):
    def test_matches_hashlib_for_passwords_and_block_boundaries(self):
        inputs = ["", "a", "abc", "message digest", "tajne heslo", "heslo ěščřžýáíé 🍲",
                  *("x" * n for n in (55, 56, 57, 63, 64, 65, 119, 120, 128))]

        result = subprocess.run(["node", "-e", RUNNER, str(MD5_JS)], input=json.dumps(inputs),
                                capture_output=True, text=True, encoding="utf-8", check=True)

        self.assertEqual(json.loads(result.stdout),
                         [hashlib.md5(s.encode()).hexdigest() for s in inputs])


if __name__ == "__main__":
    unittest.main()

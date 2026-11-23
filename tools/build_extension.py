"""Packs extension/ into dist/ffmenu-kt-<version>.zip with manifest.json at the zip root, as the Chrome Web Store wants it."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(out_dir=ROOT / "dist"):
    source = ROOT / "extension"
    version = json.loads((source / "manifest.json").read_text(encoding="utf-8"))["version"]
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"ffmenu-kt-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(source).as_posix())
    return target


if __name__ == "__main__":
    print(build())

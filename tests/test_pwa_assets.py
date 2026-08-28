import json
import struct
import unittest
from pathlib import Path

from app.main import service_worker


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        signature = image.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    return struct.unpack(">II", signature[16:24])


class PwaAssetTests(unittest.TestCase):
    def test_manifest_icons_exist_at_declared_sizes(self) -> None:
        manifest = json.loads((STATIC / "manifest.webmanifest").read_text())

        for icon in manifest["icons"]:
            path = ROOT / icon["src"].lstrip("/")
            declared = tuple(map(int, icon["sizes"].split("x")))
            self.assertTrue(path.is_file(), icon["src"])
            self.assertEqual(png_size(path), declared)

    def test_platform_icons_exist(self) -> None:
        self.assertEqual(png_size(STATIC / "icons" / "apple-touch-icon.png"), (180, 180))
        self.assertTrue((STATIC / "favicon.ico").is_file())
        self.assertTrue((STATIC / "sw.js").is_file())

    def test_service_worker_has_root_scope(self) -> None:
        response = self.run_async(service_worker())
        self.assertEqual(response.headers["service-worker-allowed"], "/")
        self.assertEqual(response.headers["cache-control"], "no-cache")

    @staticmethod
    def run_async(coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()

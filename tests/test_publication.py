import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_gtfs_update import _metadata


class PublicGtfsTests(unittest.TestCase):
    def test_manifest_and_schedule_are_consistent(self):
        source = ROOT / "pico" / "metro_schedule_data.py"
        published = ROOT / "updates" / "metro_schedule_data.py"
        manifest = json.loads(
            (ROOT / "updates" / "latest.json").read_text(encoding="utf-8")
        )
        feed, generated_at = _metadata(source)

        self.assertEqual(source.read_bytes(), published.read_bytes())
        self.assertEqual(manifest["schema"], 1)
        self.assertEqual(manifest["file"], "metro_schedule_data.py")
        self.assertEqual(manifest["size"], published.stat().st_size)
        self.assertEqual(
            manifest["sha256"],
            hashlib.sha256(published.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            (
                manifest["feed_start"],
                manifest["feed_end"],
                manifest["feed_version"],
            ),
            feed,
        )
        self.assertEqual(manifest["generated_at"], generated_at)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Publie un horaire compact et son manifeste pour la mise à jour du Pico."""

import argparse
import ast
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CURRENT = ROOT / "pico" / "metro_schedule_data.py"
DEFAULT_OUTPUT_DIR = ROOT / "updates"
DEFAULT_PACKAGED = None
SCHEDULE_FILENAME = "metro_schedule_data.py"
MANIFEST_FILENAME = "latest.json"
MAX_SCHEDULE_BYTES = 250_000


def _metadata(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"FEED", "GENERATED_AT"}
        ):
            values[node.targets[0].id] = ast.literal_eval(node.value)

    feed = values.get("FEED")
    generated_at = values.get("GENERATED_AT")
    if (
        not isinstance(feed, tuple)
        or len(feed) != 3
        or not all(isinstance(value, str) for value in feed)
        or len(feed[0]) != 8
        or len(feed[1]) != 8
        or not feed[0].isdigit()
        or not feed[1].isdigit()
    ):
        raise ValueError("Constante FEED invalide dans {}".format(path))
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("Constante GENERATED_AT invalide dans {}".format(path))
    return feed, generated_at


def _semantic_content(path):
    """Ignore seulement l'horodatage de génération lors de la comparaison."""
    lines = path.read_bytes().splitlines(keepends=True)
    return b"".join(
        line for line in lines if not line.startswith(b"GENERATED_AT = ")
    )


def _install_candidate(candidate, current, allow_older=False):
    candidate_feed, _ = _metadata(candidate)
    current_feed, _ = _metadata(current)
    if not allow_older and candidate_feed[1] < current_feed[1]:
        raise ValueError(
            "Le GTFS candidat se termine avant l'horaire actuel: {} < {}".format(
                candidate_feed[1],
                current_feed[1],
            )
        )
    if _semantic_content(candidate) == _semantic_content(current):
        return False
    shutil.copyfile(candidate, current)
    return True


def publish(current, output_dir, packaged=DEFAULT_PACKAGED):
    feed, generated_at = _metadata(current)
    schedule_size = current.stat().st_size
    if schedule_size <= 0 or schedule_size > MAX_SCHEDULE_BYTES:
        raise ValueError(
            "Taille d'horaire invalide: {} octets".format(schedule_size)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    published_schedule = output_dir / SCHEDULE_FILENAME
    shutil.copyfile(current, published_schedule)
    if packaged is not None:
        packaged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current, packaged)
    digest = hashlib.sha256(published_schedule.read_bytes()).hexdigest()
    manifest = {
        "schema": 1,
        "file": SCHEDULE_FILENAME,
        "size": schedule_size,
        "sha256": digest,
        "feed_start": feed[0],
        "feed_end": feed[1],
        "feed_version": feed[2],
        "generated_at": generated_at,
    }
    (output_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--packaged",
        type=Path,
        default=DEFAULT_PACKAGED,
    )
    parser.add_argument("--allow-older", action="store_true")
    args = parser.parse_args()

    changed = False
    if args.candidate is not None:
        changed = _install_candidate(
            args.candidate,
            args.current,
            allow_older=args.allow_older,
        )
    manifest = publish(args.current, args.output_dir, args.packaged)
    print("Horaire modifié:", "oui" if changed else "non")
    print("Période:", manifest["feed_start"], "à", manifest["feed_end"])
    print("Version:", manifest["feed_version"])
    print("Manifeste:", args.output_dir / MANIFEST_FILENAME)


if __name__ == "__main__":
    main()

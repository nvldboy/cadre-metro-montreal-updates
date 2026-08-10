#!/usr/bin/env python3
"""Convertit le GTFS STM en horaire métro compact pour le Pico et le simulateur."""

import argparse
import csv
import io
import json
import pprint
import statistics
import sys
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICO = ROOT / "pico"
STATIONS_MAP_PATH = PICO / "stations_map.json"
STATIONS_MAP = json.loads(STATIONS_MAP_PATH.read_text(encoding="utf-8"))
STATION_INDEX = {
    station_name: index
    for index, station_name in enumerate(STATIONS_MAP["stations"])
}

LINE_IDS = ("green", "orange", "yellow", "blue")
ROUTE_TO_LINE = {"1": 0, "2": 1, "4": 2, "5": 3}
LINE_PATHS = tuple(
    tuple(STATIONS_MAP["lines"][line_name]) for line_name in LINE_IDS
)


def _rows(archive, filename):
    raw = archive.open(filename)
    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    return csv.DictReader(text)


def _normalize(value):
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = (
        value.lower()
        .replace("station ", "")
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
        .replace(" -zone b", "")
        .replace(" (zone b)", "")
        .strip()
    )
    return "".join(char for char in value if char.isalnum())


def _seconds(value):
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _service_mask(row):
    fields = (
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    )
    mask = 0
    for index, field in enumerate(fields):
        if row[field] == "1":
            mask |= 1 << index
    return mask


def _follows_configured_path(station_indexes, line_index):
    path = LINE_PATHS[line_index]
    reverse_path = tuple(reversed(path))
    length = len(station_indexes)
    return any(
        candidate[start:start + length] == station_indexes
        for candidate in (path, reverse_path)
        for start in range(len(candidate) - length + 1)
    )


def build_schedule(zip_path):
    canonical = {_normalize(name): name for name in STATION_INDEX}

    with zipfile.ZipFile(zip_path) as archive:
        stop_names = {}
        for row in _rows(archive, "stops.txt"):
            normalized = _normalize(row["stop_name"])
            station_name = canonical.get(normalized)
            if station_name is not None:
                stop_names[row["stop_id"]] = station_name

        route_lines = {}
        for row in _rows(archive, "routes.txt"):
            if row.get("route_type") != "1":
                continue
            line_index = ROUTE_TO_LINE.get(row.get("route_short_name"))
            if line_index is not None:
                route_lines[row["route_id"]] = line_index

        trip_meta = {}
        service_ids = set()
        for row in _rows(archive, "trips.txt"):
            line_index = route_lines.get(row["route_id"])
            if line_index is None:
                continue
            service_ids.add(row["service_id"])
            trip_meta[row["trip_id"]] = (
                line_index,
                int(row.get("direction_id") or 0),
                row.get("trip_headsign", ""),
                row["service_id"],
            )

        trip_stops = defaultdict(list)
        for row in _rows(archive, "stop_times.txt"):
            trip_id = row["trip_id"]
            if trip_id not in trip_meta:
                continue
            station_name = stop_names.get(row["stop_id"])
            if station_name is None:
                raise ValueError(
                    "Station métro GTFS inconnue: {}".format(row["stop_id"])
                )
            passage = row.get("departure_time") or row["arrival_time"]
            trip_stops[trip_id].append((_seconds(passage), station_name))

        services = {}
        for row in _rows(archive, "calendar.txt"):
            service_id = row["service_id"]
            if service_id in service_ids:
                services[service_id] = (
                    int(row["start_date"]),
                    int(row["end_date"]),
                    _service_mask(row),
                )

        raw_exceptions = defaultdict(lambda: [set(), set()])
        for row in _rows(archive, "calendar_dates.txt"):
            service_id = row["service_id"]
            if service_id not in service_ids:
                continue
            bucket = 0 if row["exception_type"] == "1" else 1
            raw_exceptions[int(row["date"])][bucket].add(service_id)

        feed_info = next(_rows(archive, "feed_info.txt"), {})

    missing_services = service_ids.difference(services)
    if missing_services:
        raise ValueError(
            "Services métro absents de calendar.txt: "
            + ", ".join(sorted(missing_services))
        )

    ordered_services = sorted(services)
    service_index = {
        service_id: index for index, service_id in enumerate(ordered_services)
    }

    raw_patterns = defaultdict(list)
    trip_pattern_keys = {}
    for trip_id, stops in trip_stops.items():
        line_index, direction, headsign, service_id = trip_meta[trip_id]
        stops.sort()
        start = stops[0][0]
        station_indexes = tuple(
            STATION_INDEX[station_name] for _, station_name in stops
        )
        if not _follows_configured_path(station_indexes, line_index):
            raise ValueError(
                "Le voyage {} ne suit pas stations_map.json".format(trip_id)
            )
        offsets = tuple(passage - start for passage, _ in stops)
        key = (line_index, direction, station_indexes)
        raw_patterns[key].append((headsign, offsets))
        trip_pattern_keys[trip_id] = (key, service_id, start)

    patterns = []
    pattern_index = {}
    for key, samples in sorted(raw_patterns.items()):
        line_index, direction, station_indexes = key
        headsign = samples[0][0]
        offsets = tuple(
            int(statistics.median_low(sample[1][stop_index] for sample in samples))
            for stop_index in range(len(station_indexes))
        )
        pattern_index[key] = len(patterns)
        patterns.append(
            (line_index, direction, headsign, station_indexes, offsets)
        )

    grouped_departures = defaultdict(list)
    for key, service_id, start in trip_pattern_keys.values():
        grouped_departures[
            (service_index[service_id], pattern_index[key])
        ].append(start)

    departures = tuple(
        (service, pattern, tuple(sorted(times)))
        for (service, pattern), times in sorted(grouped_departures.items())
    )
    exceptions = {
        date_code: (
            tuple(sorted(service_index[item] for item in added)),
            tuple(sorted(service_index[item] for item in removed)),
        )
        for date_code, (added, removed) in sorted(raw_exceptions.items())
    }

    return {
        "feed": (
            feed_info.get("feed_start_date", ""),
            feed_info.get("feed_end_date", ""),
            feed_info.get("feed_version", ""),
        ),
        "services": tuple(services[item] for item in ordered_services),
        "exceptions": exceptions,
        "patterns": tuple(patterns),
        "departures": departures,
        "trip_count": len(trip_stops),
    }


def write_module(schedule, output_path):
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        '"""Horaire métro compact généré depuis le GTFS planifié de la STM."""',
        "",
        "# Généré automatiquement par scripts/build_metro_schedule.py.",
        "# Source: Société de transport de Montréal, licence CC BY 4.0.",
        'TIMEZONE = "America/Toronto"',
        "LINES = {!r}".format(LINE_IDS),
        "FEED = {}".format(pprint.pformat(schedule["feed"], width=100)),
        "GENERATED_AT = {!r}".format(generated_at),
        "SERVICES = {}".format(
            pprint.pformat(schedule["services"], width=100, compact=True)
        ),
        "EXCEPTIONS = {}".format(
            pprint.pformat(schedule["exceptions"], width=100, compact=True)
        ),
        "PATTERNS = {}".format(
            pprint.pformat(schedule["patterns"], width=100, compact=True)
        ),
        "DEPARTURES = {}".format(
            pprint.pformat(schedule["departures"], width=100, compact=True)
        ),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "zip_path",
        nargs="?",
        default=ROOT / "data" / "gtfs_stm.zip",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default=PICO / "metro_schedule_data.py",
        type=Path,
    )
    args = parser.parse_args()
    schedule = build_schedule(args.zip_path)
    write_module(schedule, args.output)
    print(
        "{} voyages, {} parcours types, {} groupes de départs".format(
            schedule["trip_count"],
            len(schedule["patterns"]),
            len(schedule["departures"]),
        )
    )
    print("Écrit:", args.output)


if __name__ == "__main__":
    main()

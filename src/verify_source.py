"""Independently reconcile complete private official responses and normalized public facts."""

import argparse
import csv
import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from config import ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("originals", type=Path)
    args = p.parse_args()
    m = json.loads((ROOT / "data/source/manifest.json").read_text())
    assert digest(ROOT / m["public_file"]) == m["public_sha256"]
    with gzip.open(ROOT / m["public_file"], "rt", encoding="utf-8", newline="") as f:
        stored = list(csv.DictReader(f))
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE observations(station TEXT,day TEXT,usable INT,qualified INT,PRIMARY KEY(station,day))"
    )
    expected = {}
    field_checks = 0
    stations = {r["station"]: r for r in m["stations"]}
    for page in m["pages"]:
        path = args.originals / page["original_file"]
        assert digest(path) == page["sha256"]
        j = json.loads(path.read_text())
        assert len(j["features"]) == page["rows"]
        station = stations[page["station"]]
        for feature in j["features"]:
            q = feature["properties"]
            assert (
                q["time_series_id"] == station["series"]
                and q["monitoring_location_id"] == "USGS-" + station["station"]
            )
            assert (q["parameter_code"], q["statistic_id"], q["unit_of_measure"]) == (
                "00060",
                "00003",
                "ft^3/s",
            )
            d = datetime.strptime(q["time"], "%Y-%m-%d").date()
            assert date(2019, 12, 1) <= d <= date(2025, 12, 31)
            text = q["value"] if q["value"] is not None else ""
            assert isinstance(text, str)
            valid = True
            try:
                number = Decimal(text)
            except InvalidOperation:
                valid = False
            else:
                assert number.is_finite() and number >= 0
            assert q["approval_status"] in ["Approved", "Provisional"]
            usable = valid and q["approval_status"] == "Approved"
            quality = (
                "unapproved"
                if q["approval_status"] != "Approved"
                else "usable" if valid else "missing_or_nonnumeric"
            )
            flags = q["qualifier"]
            flags = (
                []
                if flags is None
                else [flags] if isinstance(flags, str) and flags else flags
            )
            assert isinstance(flags, list)
            flagtext = json.dumps(flags, separators=(",", ":")) if flags else ""
            row = {
                "basin": station["basin"],
                "role": station["role"],
                "station": station["station"],
                "series": station["series"],
                "date": q["time"],
                "source_value": text,
                "unit": "ft^3/s",
                "approval": q["approval_status"],
                "qualifier": flagtext,
                "last_modified": q["last_modified"],
                "quality": quality,
            }
            key = station["station"], q["time"]
            assert key not in expected
            expected[key] = row
            db.execute(
                "INSERT INTO observations VALUES(?,?,?,?)",
                (key[0], key[1], int(usable), int(bool(flags))),
            )
            field_checks += 10
    actual = {(r["station"], r["date"]): r for r in stored}
    assert len(actual) == len(stored) == m["selected_rows"] and actual == expected
    for station in m["stations"]:
        for key, hashkey in [
            ("metadata_original", "metadata_sha256"),
            ("metadata_after_original", "metadata_after_sha256"),
            ("location_original", "location_sha256"),
        ]:
            assert digest(args.originals / station[key]) == station[hashkey]
        before = json.loads(
            (args.originals / station["metadata_original"]).read_text()
        )["features"][0]["properties"]
        after = json.loads(
            (args.originals / station["metadata_after_original"]).read_text()
        )["features"][0]["properties"]
        assert (
            before["id"] == after["id"] == station["series"]
            and before["last_modified"]
            == after["last_modified"]
            == station["source_version"]
        )
        assert (
            before["primary"],
            before["computation_period_identifier"],
            before["computation_identifier"],
            before["unit_of_measure"],
        ) == ("Primary", "Daily", "Mean", "ft^3/s")
        location = json.loads(
            (args.originals / station["location_original"]).read_text()
        )["properties"]
        assert (
            location["monitoring_location_name"] == station["name"]
            and location["id"] == "USGS-" + station["station"]
        )
    with (ROOT / "data/measurements.csv").open(encoding="utf-8", newline="") as f:
        normalized = list(csv.DictReader(f))
    columns = ["basin", "role", "station", "date", "source_value", "qualifier"]
    want = [{k: r[k] for k in columns} for r in stored if r["quality"] == "usable"]
    assert normalized == want
    with (ROOT / "results/source_coverage.csv").open(encoding="utf-8") as f:
        coverage = list(csv.DictReader(f))
    for r in coverage:
        year = int(r["year"])
        n, usable, qualified = db.execute(
            "SELECT COUNT(*),SUM(usable),SUM(CASE WHEN usable=1 THEN qualified ELSE 0 END) FROM observations WHERE station=? AND substr(day,1,4)=?",
            (r["station"], r["year"]),
        ).fetchone()
        days = 366 if year in [2020, 2024] else 365
        assert [
            int(r[k])
            for k in [
                "source_rows",
                "usable_approved_days",
                "qualified_usable_days",
                "calendar_days",
                "missing_or_unusable_days",
            ]
        ] == [n, usable, qualified, days, days - usable]
        assert usable * 100 >= 95 * days
    cert = {
        "status": "PASS",
        "source_rows": len(stored),
        "selected_source_field_checks": field_checks,
        "projected_scalar_checks": len(stored) * 11,
        "normalized_scalar_checks": len(normalized) * 6,
        "station_year_checks": len(coverage),
        "public_aggregate_sha256": m["public_sha256"],
        "public_manifest_sha256": hashlib.sha256(
            (ROOT / "data/source/manifest.json").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "methods": "Complete independent source-row map using strptime/Decimal; SQLite unique station/date and coverage counts; all private response, metadata and public hashes reconciled",
        "limits": "Selected public gauge facts verified; no historical operational-vintage or hydrologic causal claim",
    }
    (ROOT / "results/INDEPENDENT_SOURCE_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    main()

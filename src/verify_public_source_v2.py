"""Check public projection consistency; native-original evidence stays separately hash-bound."""

import csv, gzip, hashlib, io, json, sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "data/v2"
    m = json.loads((folder / "source_manifest.json").read_bytes())
    data = (folder / "source_cells.csv.gz").read_bytes()
    assert hashlib.sha256(data).hexdigest() == m["public_sha256"]
    source = list(csv.DictReader(io.StringIO(gzip.decompress(data).decode())))
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE cells(site TEXT,day TEXT,usable INT,flag INT,PRIMARY KEY(site,day))"
    )
    normalized = []
    for r in source:
        assert m["start"] <= r["date"] <= m["end"] and r["unit"] == "ft^3/s"
        q = Decimal(r["source_value"])
        assert (
            q.is_finite()
            and q >= 0
            and r["approval"] == "Approved"
            and r["quality"] == "usable"
        )
        normalized.append(
            {
                k: r[k]
                for k in [
                    "basin",
                    "role",
                    "station",
                    "date",
                    "source_value",
                    "qualifier",
                ]
            }
        )
        db.execute(
            "INSERT INTO cells VALUES(?,?,?,?)",
            (r["station"], r["date"], 1, int(bool(r["qualifier"]))),
        )
    with (folder / "measurements.csv").open(encoding="utf-8", newline="") as f:
        assert list(csv.DictReader(f)) == normalized
    with (folder / "source_coverage.csv").open(encoding="utf-8", newline="") as f:
        coverage = list(csv.DictReader(f))
    assert len(coverage) == 40 and len(source) == m["selected_rows"] == 14864
    for r in coverage:
        year = int(r["year"])
        days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
        n, u, q = db.execute(
            "SELECT COUNT(*),SUM(usable),SUM(flag) FROM cells WHERE site=? AND substr(day,1,4)=?",
            (r["station"], str(year)),
        ).fetchone()
        assert [n, u, q, days, days - u] == [
            int(r[k])
            for k in [
                "source_rows",
                "usable_approved_days",
                "qualified_usable_days",
                "calendar_days",
                "missing_or_unusable_days",
            ]
        ]
        assert u * 100 >= 95 * days
    native = json.loads((folder / "INDEPENDENT_SOURCE_CHECK.json").read_bytes())
    assert (
        native["status"] == "PASS_INDEPENDENT_V2_SOURCE"
        and native["public_aggregate_sha256"] == m["public_sha256"]
    )
    assert (
        native["public_manifest_sha256"]
        == hashlib.sha256((folder / "source_manifest.json").read_bytes()).hexdigest()
    )
    print(
        json.dumps(
            dict(
                status="PASS_PUBLIC_V2_PROJECTION_CONSISTENCY",
                source_rows=len(source),
                coverage_gates=40,
                original_v1_gate="FAILED_UNCHANGED",
                limitation="Offline public-cell/SQL checks and original hash-bound native certificate; does not reacquire mutable historical API responses.",
            )
        )
    )


if __name__ == "__main__":
    main()

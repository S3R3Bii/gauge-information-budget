"""Capture fixed official gauge series; retain originals outside Git and publish selected facts."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from config import ROOT, PAIRS, START, END


BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/"
FIELDS = [
    "basin",
    "role",
    "station",
    "series",
    "date",
    "source_value",
    "unit",
    "approval",
    "qualifier",
    "last_modified",
    "quality",
]


def get(url):
    with urlopen(
        Request(url, headers={"User-Agent": "IndependentGaugeInformationResearch/1.0"}),
        timeout=90,
    ) as response:
        assert response.status == 200
        data = response.read()
    return data, json.loads(data)


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode())


def project(properties, basin, role, station, series):
    p = properties
    assert (
        p["monitoring_location_id"] == "USGS-" + station
        and p["time_series_id"] == series
    )
    assert (
        p["parameter_code"] == "00060"
        and p["statistic_id"] == "00003"
        and p["unit_of_measure"] == "ft^3/s"
    )
    day = date.fromisoformat(p["time"])
    assert START <= day.isoformat() <= END
    value = p["value"]
    assert value is None or isinstance(value, str)
    quality = "usable"
    text = "" if value is None else value
    try:
        q = Decimal(text)
    except InvalidOperation:
        quality = "missing_or_nonnumeric"
    else:
        assert q.is_finite() and q >= 0, "Invalid numeric flow"
    approval = p["approval_status"]
    assert approval in ["Approved", "Provisional"]
    if approval != "Approved":
        quality = "unapproved"
    qualifier = p["qualifier"]
    assert qualifier is None or isinstance(qualifier, str) and len(qualifier) <= 64
    modified = p["last_modified"]
    assert isinstance(modified, str)
    return dict(
        zip(
            FIELDS,
            [
                basin,
                role,
                station,
                series,
                day.isoformat(),
                text,
                p["unit_of_measure"],
                approval,
                qualifier or "",
                modified,
                quality,
            ],
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("originals", type=Path)
    a = parser.parse_args()
    raw = a.originals.resolve()
    assert not raw.is_relative_to(ROOT)
    raw.mkdir(parents=True, exist_ok=False)
    pages = []
    stations = []
    rows = []
    versions = {}
    seen = set()
    for basin, pair in PAIRS.items():
        for role, site in zip(["target", "additional"], pair):
            station, series = site["site"], site["series"]
            url = (
                BASE
                + "time-series-metadata/items?"
                + urlencode(
                    {
                        "f": "json",
                        "monitoring_location_id": "USGS-" + station,
                        "parameter_code": "00060",
                        "statistic_id": "00003",
                        "limit": 20,
                    }
                )
            )
            data, j = get(url)
            name = station + "-metadata-before.json"
            (raw / name).write_bytes(data)
            selected = [
                x["properties"]
                for x in j["features"]
                if x["properties"]["id"] == series
            ]
            assert len(selected) == 1 and len(j["features"]) == 1
            p = selected[0]
            assert (
                p["primary"] == "Primary"
                and p["unit_of_measure"] == "ft^3/s"
                and p["computation_period_identifier"] == "Daily"
                and p["computation_identifier"] == "Mean"
            )
            versions[station] = p["last_modified"]
            location_url = BASE + f"monitoring-locations/items/USGS-{station}?f=json"
            locbytes, location = get(location_url)
            locname = station + "-location.json"
            (raw / locname).write_bytes(locbytes)
            assert location["properties"]["id"] == "USGS-" + station
            stations.append(
                {
                    "basin": basin,
                    "role": role,
                    "station": station,
                    "series": series,
                    "name": location["properties"]["monitoring_location_name"],
                    "unit": "ft^3/s",
                    "metadata_url": url,
                    "metadata_original": name,
                    "metadata_sha256": hashlib.sha256(data).hexdigest(),
                    "source_version": p["last_modified"],
                    "location_url": location_url,
                    "location_original": locname,
                    "location_sha256": hashlib.sha256(locbytes).hexdigest(),
                }
            )
            url = (
                BASE
                + "daily/items?"
                + urlencode(
                    {
                        "f": "json",
                        "monitoring_location_id": "USGS-" + station,
                        "time_series_id": series,
                        "parameter_code": "00060",
                        "statistic_id": "00003",
                        "time": START + "T00:00:00Z/" + END + "T23:59:59Z",
                        "limit": 10000,
                    }
                )
            )
            number = 0
            count = 0
            while url:
                assert url.startswith(BASE + "daily/items?") and number < 3
                data, j = get(url)
                name = f"{station}-daily-{number}.json"
                (raw / name).write_bytes(data)
                for feature in j["features"]:
                    r = project(feature["properties"], basin, role, station, series)
                    key = station, r["date"]
                    assert key not in seen, "Duplicate station/date"
                    seen.add(key)
                    rows.append(r)
                pages.append(
                    {
                        "station": station,
                        "series": series,
                        "page": number,
                        "url": url,
                        "original_file": name,
                        "captured_utc": datetime.now(timezone.utc).isoformat(),
                        "bytes": len(data),
                        "rows": len(j["features"]),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                count += len(j["features"])
                next_links = [x["href"] for x in j["links"] if x.get("rel") == "next"]
                assert len(next_links) <= 1
                url = next_links[0] if next_links else None
                number += 1
            print(json.dumps({"station": station, "source_rows": count}), flush=True)
            save(
                raw / "CAPTURE_PROGRESS.json",
                {"state": "CAPTURING", "pages": pages, "stations": stations},
            )
    for station in stations:
        data, j = get(station["metadata_url"])
        name = station["station"] + "-metadata-after.json"
        (raw / name).write_bytes(data)
        assert len(j["features"]) == 1
        assert (
            j["features"][0]["properties"]["last_modified"]
            == versions[station["station"]]
        ), "Metadata version changed; do not refresh silently"
        station.update(
            metadata_after_original=name,
            metadata_after_sha256=hashlib.sha256(data).hexdigest(),
        )
    rows.sort(key=lambda r: (r["station"], r["date"]))
    buffer = io.StringIO(newline="")
    w = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out = ROOT / "data/source/observations.csv.gz"
    out.write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    manifest = {
        "source": "USGS daily mean discharge",
        "parameter_code": "00060",
        "statistic_id": "00003",
        "start": START,
        "end": END,
        "captured_date_utc": datetime.now(timezone.utc).date().isoformat(),
        "stations": stations,
        "pages": pages,
        "selected_rows": len(rows),
        "public_file": "data/source/observations.csv.gz",
        "public_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "boundary": "Selected public gauge facts; complete response originals/documents outside Git. Later approved records do not establish historical input availability; metadata consistency is not an atomic snapshot guarantee.",
    }
    save(ROOT / "data/source/manifest.json", manifest)
    save(
        raw / "CAPTURE_PROGRESS.json",
        {
            "state": "COMPLETE",
            "selected_rows": len(rows),
            "public_sha256": manifest["public_sha256"],
        },
    )
    print(
        json.dumps({"status": "CAPTURED", "rows": len(rows), "stations": len(stations)})
    )


if __name__ == "__main__":
    main()

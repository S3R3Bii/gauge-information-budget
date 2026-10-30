"""Independently bind source values, intervals, SVG geometry, labels and heatmap colors."""

import hashlib, json, math, re
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
S = "{http://www.w3.org/2000/svg}"
read = lambda n: json.loads((ROOT / n).read_bytes())


def vertices(node):
    path = node.find(".//" + S + "path")
    assert path is not None
    numbers = [
        float(v)
        for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.attrib["d"])
    ]
    assert len(numbers) % 2 == 0
    return list(zip(numbers[::2], numbers[1::2]))


def main():
    maps = read("figures/value_map.json")
    primary = read("results/v2/final/summary.json")["primary_panels"]
    boot = read("results/v2/final/bootstrap.json")
    panels = read("results/v2/final/panel_metrics.json")
    validation = read("results/v2/development/candidate_scores.json")
    selected = read("results/v2/development/selection.json")["selected"]
    values = coordinates = labels = hashes = colors = 0
    assert set(maps) == {"primary_gauge_skill", "gauge_sensitivity", "gauge_validation"}
    for name, mapping in maps.items():
        tree = ElementTree.parse(ROOT / "figures" / (name + ".svg"))
        ids = {n.get("id"): n for n in tree.iter() if n.get("id")}
        areas = []
        for i in range(len(mapping["axes"])):
            pp = vertices(ids["data-area-" + str(i)])
            areas.append(
                (
                    min(x for x, y in pp),
                    max(x for x, y in pp),
                    min(y for x, y in pp),
                    max(y for x, y in pp),
                )
            )
        assert (
            len(mapping["items"])
            == {
                "primary_gauge_skill": 8,
                "gauge_sensitivity": 64,
                "gauge_validation": 4,
            }[name]
        )
        for item in mapping["items"]:
            axis = mapping["axes"][item["axes"]]
            xmin, xmax, ymin, ymax = areas[item["axes"]]

            def project(point):
                x, y = point
                xl, xr = axis["xlim"]
                yl, yr = axis["ylim"]
                return xmin + (x - xl) / (xr - xl) * (xmax - xmin), ymax - (y - yl) / (
                    yr - yl
                ) * (ymax - ymin)

            def actual_matches(gid, points):
                nonlocal coordinates
                actual = vertices(ids[gid])
                expected = [project(p) for p in points]
                assert len(actual) in [len(expected), len(expected) + 1], (
                    gid,
                    actual,
                    expected,
                )
                for pair, target in zip(actual, expected):
                    for a, b in zip(pair, target):
                        assert abs(a - b) <= 3e-5, (gid, a, b)
                        coordinates += 1

            if item["kind"] == "bar":
                _, index, model = item["id"].split("-")
                index = int(index)
                row = primary[index]
                value = row[model + "_skill"] * 100
                interval = next(x for x in boot if x["panel"] == row["panel"])[
                    "conditional_90_percent_intervals"
                ][model + "_skill"]
                lo, hi = interval["lower"] * 100, interval["upper"] * 100
                y = index + (-0.17 if model == "local" else 0.17)
                assert (
                    item["value"] == value
                    and item["interval"] == [lo, hi]
                    and item["y"] == y
                    and item["half_height"] == 0.14
                )
                assert axis == dict(xlim=[-5, 60], ylim=[3.55, -0.55])
                values += 3
                assert axis["xlim"][0] <= lo <= value <= hi <= axis["xlim"][1]
                actual_matches(
                    item["id"],
                    [
                        (0, y - 0.14),
                        (value, y - 0.14),
                        (value, y + 0.14),
                        (0, y + 0.14),
                    ],
                )
                actual_matches(item["id"] + "-interval", [(lo, y), (hi, y)])
            elif item["kind"] == "cell":
                _, i, j = item["id"].split("-")
                i, j = int(i), int(j)
                basin = ["wisconsin", "delaware", "susquehanna", "mississippi"][i // 2]
                year = [2023, 2024][i % 2]
                column = [
                    (l, s, q)
                    for l in [3, 1]
                    for s in ["normal", "seven-day-outage"]
                    for q in ["all-approved", "empty-qualifiers"]
                ][j]
                rr = [
                    r
                    for r in panels
                    if r["basin"] == basin
                    and r["year"] == year
                    and (r["lag"], r["scenario"], r["qualifier_rule"]) == column
                ]
                pair = next(r for r in rr if r["model"] == "pair")
                local = next(r for r in rr if r["model"] == "local")
                value = (
                    pair["log_mse_skill_vs_persistence"]
                    - local["log_mse_skill_vs_persistence"]
                ) * 100
                assert (
                    item["value"] == value
                    and item["x"] == j
                    and item["y"] == i
                    and axis == dict(xlim=[-0.5, 7.5], ylim=[7.5, -0.5])
                )
                values += 1
                actual_matches(
                    item["id"],
                    [
                        (j - 0.5, i - 0.5),
                        (j + 0.5, i - 0.5),
                        (j + 0.5, i + 0.5),
                        (j - 0.5, i + 0.5),
                    ],
                )
                rgb0 = (246, 247, 248)
                rgb1 = (34, 96, 122) if value >= 0 else (163, 67, 58)
                f = min(abs(value) / 50, 1)
                expected_color = "#" + "".join(
                    f"{round(a+(b-a)*f):02x}" for a, b in zip(rgb0, rgb1)
                )
                assert item["color"] == expected_color
                path = ids[item["id"]].find(".//" + S + "path")
                assert "fill: " + expected_color in path.attrib["style"]
                colors += 1
            else:
                assert item["kind"] == "line"
                _, lag, model = item["id"].split("-")
                lag = int(lag)
                rr = sorted(
                    [r for r in validation if r["lag"] == lag and r["model"] == model],
                    key=lambda r: r["penalty"],
                )
                xx = [-3, -2, -1, 0]
                yy = [r["equal_basin_validation_log_mse"] for r in rr]
                index = next(
                    i
                    for i, r in enumerate(rr)
                    if r["penalty"] == selected[f"lag{lag}--{model}"]
                )
                assert (
                    item["x"] == xx
                    and item["y"] == yy
                    and item["selected_index"] == index
                )
                values += 5
                maximum = max(
                    r["equal_basin_validation_log_mse"]
                    for r in validation
                    if r["lag"] == lag
                )
                assert axis == dict(
                    xlim=[-3.15, 0.15],
                    ylim=[0, math.ceil(maximum * 1.12 / 0.01) * 0.01],
                )
                actual_matches(item["id"], list(zip(xx, yy)))
                use = ids[item["id"] + "-selected"].find(".//" + S + "use")
                assert use is not None
                target = project((xx[index], yy[index]))
                assert all(
                    abs(float(use.attrib[k]) - v) <= 3e-5
                    for k, v in zip(["x", "y"], target)
                )
                coordinates += 2
                continue
            expected_label = f"{value:.1f}"
            assert item["label"] == expected_label
            text = " ".join("".join(ids[item["id"] + "-label"].itertext()).split())
            assert text == expected_label
            labels += 1
        for ext, digest in mapping["sha256"].items():
            assert (
                hashlib.sha256(
                    (ROOT / "figures" / (name + "." + ext)).read_bytes()
                ).hexdigest()
                == digest
            )
            hashes += 1
        assert (ROOT / "paper/images" / (name + ".pdf")).read_bytes() == (
            ROOT / "figures" / (name + ".pdf")
        ).read_bytes()
    result = dict(
        status="PASS_SOURCE_VALUES_AND_ACTUAL_SVG",
        figures=3,
        mapped_source_values=values,
        svg_coordinates=coordinates,
        individual_numeric_labels=labels,
        source_bound_cell_colors=colors,
        file_hashes=hashes,
        source="Primary skills and intervals; all64 sensitivity comparisons; all16 validation objectives and4 selections",
        limitation="Figure-specific geometry/value/color checks plus separate visual review; no accessibility-conformance claim.",
    )
    (ROOT / "figures/verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()

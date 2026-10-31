"""Render all primary results, full declared sensitivity and every validation candidate."""

import hashlib, json, math, platform, shutil
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "svg.fonttype": "none",
        "svg.hashsalt": "gauge14-v2",
        "path.simplify": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "text.color": "#203d4b",
        "axes.labelcolor": "#203d4b",
    }
)
read = lambda n: json.loads((ROOT / n).read_bytes())
MAP = {}


def axes_map(ax):
    return dict(xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim()))


def save(fig, name, items, axes):
    for i, ax in enumerate(fig.axes):
        ax.patch.set_gid("data-area-" + str(i))
    folder = ROOT / "figures"
    folder.mkdir(exist_ok=True)
    images = ROOT / "paper/images"
    images.mkdir(parents=True, exist_ok=True)
    fig.savefig(folder / (name + ".svg"), metadata={"Date": None})
    svg = folder / (name + ".svg")
    svg.write_bytes(
        (
            "\n".join(
                line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()
            )
            + "\n"
        ).encode()
    )
    fig.savefig(
        folder / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None}
    )
    fig.savefig(folder / (name + ".png"), dpi=150)
    shutil.copyfile(folder / (name + ".pdf"), images / (name + ".pdf"))
    MAP[name] = dict(
        items=items,
        axes=axes,
        sha256={
            ext: hashlib.sha256((folder / (name + "." + ext)).read_bytes()).hexdigest()
            for ext in ["svg", "pdf", "png"]
        },
    )
    plt.close(fig)


def title(fig, heading, sub):
    fig.text(0.23, 0.965, heading, ha="left", va="top", fontsize=15, weight="bold")
    fig.text(0.23, 0.90, sub, ha="left", va="top", fontsize=9)


def primary():
    summary = read("results/v2/final/summary.json")["primary_panels"]
    boot = read("results/v2/final/bootstrap.json")
    fig, ax = plt.subplots(figsize=(8.8, 5.5))
    fig.subplots_adjust(left=0.23, right=0.96, top=0.78, bottom=0.26)
    title(
        fig,
        "One extra gauge improves log-flow prediction",
        "Three-day lag; four basin/year panels held out of configuration selection.",
    )
    items = []
    labels = []
    for i, row in enumerate(summary):
        b = next(x for x in boot if x["panel"] == row["panel"])
        labels.append(row["panel"].replace("--", " ") + f"\n(n={row['n']} days)")
        for model, dy, color in [
            ("local", -0.17, "#79858d"),
            ("pair", 0.17, "#24627b"),
        ]:
            v = row[model + "_skill"] * 100
            y = i + dy
            gid = f"primary-{i}-{model}"
            ax.barh([y], [v], height=0.28, color=color)[0].set_gid(gid)
            interval = b["conditional_90_percent_intervals"][model + "_skill"]
            lo = interval["lower"] * 100
            hi = interval["upper"] * 100
            ax.plot([lo, hi], [y, y], color="#162e3b", linewidth=1.5)[0].set_gid(
                gid + "-interval"
            )
            ax.text(hi + 1, y, f"{v:.1f}", va="center", fontsize=9).set_gid(
                gid + "-label"
            )
            items.append(
                dict(
                    id=gid,
                    kind="bar",
                    axes=0,
                    value=v,
                    y=y,
                    half_height=0.14,
                    label=f"{v:.1f}",
                    interval=[lo, hi],
                )
            )
    ax.set_yticks(range(4), labels)
    ax.set_ylim(3.55, -0.55)
    ax.set_xlim(-5, 60)
    ax.set_xlabel("Log-MSE skill versus persistence (%)")
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
    ax.axvline(0, color="#526b78", linestyle="--", linewidth=0.8)
    fig.text(
        0.23,
        0.13,
        "Grey: local history. Blue: one extra gauge. Numbers: point estimates; lines: 90% intervals.",
        fontsize=8,
    )
    fig.text(
        0.23,
        0.065,
        "Later Approved records under synthetic lags; these intervals do not establish future coverage.",
        fontsize=8,
    )
    save(fig, "primary_gauge_skill", items, [axes_map(ax)])


def color(value):
    neutral = (246, 247, 248)
    end = (34, 96, 122) if value >= 0 else (163, 67, 58)
    fraction = min(abs(value) / 50, 1)
    return "#" + "".join(f"{round(a+(b-a)*fraction):02x}" for a, b in zip(neutral, end))


def sensitivity():
    metrics = read("results/v2/final/panel_metrics.json")
    fig, ax = plt.subplots(figsize=(8.8, 6.3))
    fig.subplots_adjust(left=0.23, right=0.97, top=0.76, bottom=0.25)
    title(
        fig,
        "Sensitivity to lag, outage and qualifier rules",
        "Cells: pair minus local skill, in percentage points of persistence-normalized log MSE.",
    )
    rows = [
        (b, y)
        for b in ["wisconsin", "delaware", "susquehanna", "mississippi"]
        for y in [2023, 2024]
    ]
    columns = [
        (lag, scenario, qualifier)
        for lag in [3, 1]
        for scenario in ["normal", "seven-day-outage"]
        for qualifier in ["all-approved", "empty-qualifiers"]
    ]
    items = []
    for i, (basin, year) in enumerate(rows):
        for j, (lag, scenario, qualifier) in enumerate(columns):
            rr = [
                r
                for r in metrics
                if r["basin"] == basin
                and r["year"] == year
                and r["lag"] == lag
                and r["scenario"] == scenario
                and r["qualifier_rule"] == qualifier
            ]
            pair = next(r for r in rr if r["model"] == "pair")
            local = next(r for r in rr if r["model"] == "local")
            v = (
                pair["log_mse_skill_vs_persistence"]
                - local["log_mse_skill_vs_persistence"]
            ) * 100
            gid = f"sensitivity-{i}-{j}"
            ax.add_patch(
                Rectangle(
                    (j - 0.5, i - 0.5),
                    1,
                    1,
                    facecolor=color(v),
                    edgecolor="white",
                    linewidth=1,
                    gid=gid,
                )
            )
            ax.text(
                j,
                i,
                f"{v:.1f}",
                ha="center",
                va="center",
                fontsize=9,
                color="white" if v > 40 else "#162e3b",
            ).set_gid(gid + "-label")
            items.append(
                dict(
                    id=gid,
                    kind="cell",
                    axes=0,
                    value=v,
                    x=j,
                    y=i,
                    color=color(v),
                    label=f"{v:.1f}",
                )
            )
    ax.set_xlim(-0.5, 7.5)
    ax.set_ylim(7.5, -0.5)
    ax.set_yticks(
        range(8),
        [
            b.title()
            + " "
            + str(y)
            + (" (context)" if b in ["wisconsin", "delaware"] else "")
            for b, y in rows
        ],
    )
    ax.set_xticks(
        range(8),
        [
            f"{l}d\n{'normal' if s=='normal' else 'outage'}\n{'all' if q=='all-approved' else 'clean'}"
            for l, s, q in columns
        ],
        fontsize=8,
    )
    ax.tick_params(length=0)
    for i in [1.5, 3.5, 5.5]:
        ax.axhline(i, color="#526b78", linewidth=0.8)
    fig.text(
        0.23,
        0.16,
        "All: Approved support. Clean: no qualifier on target or any required input.",
        fontsize=8,
    )
    fig.text(
        0.23,
        0.12,
        "Models share dates within each cell; qualifier rules can change the denominator.",
        fontsize=8,
    )
    fig.text(
        0.23,
        0.08,
        "Colour range fixed at −50 to +50 points: red (negative), white (zero), blue (positive).",
        fontsize=8,
    )
    fig.text(
        0.23,
        0.04,
        "No operational-vintage or measured sensor-cost benefit. Full cfs errors are retained separately.",
        fontsize=8,
    )
    save(fig, "gauge_sensitivity", items, [axes_map(ax)])


def validation():
    data = read("results/v2/development/candidate_scores.json")
    selection = read("results/v2/development/selection.json")["selected"]
    fig, aa = plt.subplots(1, 2, figsize=(8.8, 4.7))
    fig.subplots_adjust(left=0.10, right=0.97, top=0.70, bottom=0.22, wspace=0.30)
    fig.text(
        0.10,
        0.95,
        "All validation candidates remain visible",
        fontsize=15,
        weight="bold",
    )
    fig.text(
        0.10,
        0.86,
        "Wisconsin and Delaware, 2022; common support, equal-basin log-MSE selection.",
        fontsize=9,
    )
    items = []
    for a, lag in enumerate([3, 1]):
        ax = aa[a]
        maximum = 0
        for model, color in [("local", "#79858d"), ("pair", "#24627b")]:
            rr = sorted(
                [r for r in data if r["lag"] == lag and r["model"] == model],
                key=lambda r: r["penalty"],
            )
            values = [r["equal_basin_validation_log_mse"] for r in rr]
            maximum = max(maximum, max(values))
            gid = f"validation-{lag}-{model}"
            ax.plot([-3, -2, -1, 0], values, color=color, marker="o", label=model)[
                0
            ].set_gid(gid)
            chosen = selection[f"lag{lag}--{model}"]
            index = next(i for i, r in enumerate(rr) if r["penalty"] == chosen)
            ax.plot(
                [[-3, -2, -1, 0][index]],
                [values[index]],
                marker="*",
                markersize=13,
                color=color,
            )[0].set_gid(gid + "-selected")
            items.append(
                dict(
                    id=gid,
                    kind="line",
                    axes=a,
                    x=[-3, -2, -1, 0],
                    y=values,
                    selected_index=index,
                )
            )
        ax.set_xlim(-3.15, 0.15)
        ax.set_ylim(0, math.ceil(maximum * 1.12 / 0.01) * 0.01)
        ax.set_xticks([-3, -2, -1, 0], ["0.001", "0.01", "0.1", "1"])
        ax.set_xlabel("Penalty λ (logarithmic spacing)")
        ax.set_ylabel("Validation MSE (log-flow squared)")
        ax.set_title(f"{lag}-day lag")
        ax.grid(alpha=0.15)
        ax.legend(frameon=False, fontsize=9)
    fig.text(
        0.10,
        0.095,
        "Stars: selected penalties. The one-day pair winner is on the lower grid boundary; no extension.",
        fontsize=8,
    )
    save(fig, "gauge_validation", items, [axes_map(ax) for ax in aa])


if __name__ == "__main__":
    primary()
    sensitivity()
    validation()
    (ROOT / "figures/value_map.json").write_bytes(
        (json.dumps(MAP, indent=2) + "\n").encode()
    )
    (ROOT / "figures/render_runtime.json").write_bytes(
        (
            json.dumps(
                dict(
                    python=platform.python_version(),
                    matplotlib=matplotlib.__version__,
                    font="DejaVu Sans",
                ),
                indent=2,
            )
            + "\n"
        ).encode()
    )
    print(
        "Rendered three source-bound figures in PDF/SVG/PNG; independent checks and inspection pending."
    )

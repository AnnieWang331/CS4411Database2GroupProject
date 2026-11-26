"""Draw the report's benchmark charts from saved results (needs matplotlib).

Usage:
  python scripts/bench_charts.py --run RUN_ID [--provisioned-run RUN_ID] [--live-run RUN_ID]
         [--out benchmarks/charts]

``--run`` is a ``benchmark.py run`` with the default scenarios (hot-room, many-rooms,
no-room-check, hot-idea, query-vs-scan); ``--provisioned-run`` a hot-room run on a provisioned
table; ``--live-run`` a ``benchmark.py live`` run. Each chart is saved as PNG (for Overleaf) and
the numbers behind it are in the run's CSVs.
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 - after choosing the non-interactive backend

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "benchmarks" / "results"
OUT = ROOT / "benchmarks" / "charts"

# Categorical slots in fixed order (validated palette, light mode); ink for all text.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
LABELS = {
    "hot-room": "One room",
    "many-rooms": "10 rooms",
    "no-room-check": "One room, no room check",
    "hot-idea": "Everyone votes on one idea",
}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "font.size": 9,
        "legend.frameon": False,
        "legend.labelcolor": INK,
        "lines.linewidth": 2,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)


def read(run_id: str, name: str) -> list[dict[str, str]]:
    with (RESULTS / f"bench-{run_id}-{name}.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def pick(rows, scenario: str, op: str, field: str) -> dict[int, float]:
    """``{students: value}`` for one scenario and op."""
    return {
        int(r["students"]): float(r[field])
        for r in rows
        if r["scenario"] == scenario and r["op"] == op
    }


def end_labels(ax, points: list[tuple[float, float]]) -> None:
    """Label each line's last value, nudging labels apart so close values don't overlap."""
    ax.set_ylim(bottom=0)
    lo, hi = ax.get_ylim()
    x_lo, x_hi = ax.get_xlim()
    ax.set_xlim(x_lo, x_hi + (x_hi - x_lo) * 0.18)  # room for the labels inside the panel
    dx, min_gap = (x_hi - x_lo) * 0.03, (hi - lo) * 0.07
    placed: list[float] = []
    for x, y in sorted(points, key=lambda p: p[1]):
        shown = max(y, placed[-1] + min_gap) if placed else y
        placed.append(shown)
        ax.text(x + dx, shown, f"{y:,.0f}", va="center", color=INK)


def lines(ax, rows, scenarios: list[str], op: str, field: str) -> None:
    """One line per scenario over the student counts, labelled at its last point."""
    ends = []
    for color, scenario in zip(SERIES, scenarios, strict=False):
        values = pick(rows, scenario, op, field)
        if not values:
            continue
        xs = sorted(values)
        ys = [values[x] for x in xs]
        ax.plot(xs, ys, color=color, marker="o", markersize=6, label=LABELS[scenario])
        ends.append((xs[-1], ys[-1]))
    ax.set_xticks(sorted({int(r["students"]) for r in rows if r["op"] == op}))
    ax.set_xlabel("Students")
    end_labels(ax, ends)


def legend_below(fig, ax) -> None:
    """One legend under the figure, so it never covers a line."""
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncols=len(labels), bbox_to_anchor=(0.5, -0.08))


def save(fig, name: str, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    print(path)
    return path


def vote_latency(run_id: str, out: Path) -> Path:
    rows = read(run_id, "summary")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    scenarios = ["hot-room", "many-rooms", "no-room-check"]
    for ax, field, title in [(axes[0], "p50_ms", "Median"), (axes[1], "p95_ms", "95th pct")]:
        lines(ax, rows, scenarios, "vote", field)
        ax.set_title(f"Vote latency, {title} (ms)")
    legend_below(fig, axes[0])
    return save(fig, "vote-latency", out)


def throughput(run_id: str, out: Path) -> Path:
    phases = read(run_id, "phases")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    for ax, ph, title in [(axes[0], "post", "Posts"), (axes[1], "vote", "Votes")]:
        rows = [
            {"scenario": p["scenario"], "students": p["students"], "op": ph, "v": p["ops_per_s"]}
            for p in phases
            if p["phase"] == ph
        ]
        lines(ax, rows, ["hot-room", "many-rooms", "no-room-check"], ph, "v")
        ax.set_title(f"{title} per second")
    legend_below(fig, axes[0])
    return save(fig, "throughput", out)


def conflicts(run_id: str, out: Path) -> Path:
    rows = read(run_id, "summary")
    scenarios = ["hot-room", "no-room-check", "hot-idea"]
    counts = sorted({int(r["students"]) for r in rows if r["scenario"] in scenarios})
    fig, ax = plt.subplots(figsize=(8, 3.2))
    width = 0.8 / len(scenarios)
    for i, (color, scenario) in enumerate(zip(SERIES, scenarios, strict=True)):
        conflicts_ = pick(rows, scenario, "vote", "tx_conflicts")
        totals = pick(rows, scenario, "vote", "count")
        per_vote = [conflicts_.get(n, 0) / totals[n] if totals.get(n) else 0 for n in counts]
        xs = [c + (i - 1) * width for c in range(len(counts))]
        bars = ax.bar(
            xs, per_vote, width, color=color, edgecolor=SURFACE, linewidth=2, label=LABELS[scenario]
        )
        ax.bar_label(bars, fmt="%.2f", padding=2, color=INK, fontsize=8)
    ax.set_xticks(range(len(counts)), [f"{n} students" for n in counts])
    ax.set_title("Transaction conflicts per vote")
    ax.set_ylim(bottom=0, top=max(ax.get_ylim()[1], 0.1))
    legend_below(fig, ax)
    return save(fig, "conflicts", out)


def query_vs_scan(run_id: str, out: Path) -> Path:
    rows = {r["op"]: r for r in read(run_id, "summary") if r["scenario"] == "query-vs-scan"}
    ops = [("board_query", "Query (one partition)"), ("board_scan", "Scan + filter")]
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.6))
    for ax, field, title in [
        (axes[0], "p50_ms", "Median latency (ms)"),
        (axes[1], "capacity_per_op", "Read capacity per board load"),
    ]:
        values = [float(rows[op][field]) for op, _ in ops]
        bars = ax.barh(
            [label for _, label in ops], values, color=SERIES[0], edgecolor=SURFACE, linewidth=2
        )
        ax.bar_label(bars, fmt="%.1f", padding=3, color=INK)
        ax.set_title(title)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.invert_yaxis()
        ax.margins(x=0.2)
    axes[1].set_yticklabels([])
    return save(fig, "query-vs-scan", out)


def capacity_modes(run_id: str, provisioned_id: str, out: Path) -> Path:
    on_demand, provisioned = read(run_id, "summary"), read(provisioned_id, "summary")
    counts = sorted(set(pick(provisioned, "hot-room", "vote", "p95_ms")))
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2))
    for ax, field, title in [
        (axes[0], "p95_ms", "Vote latency, 95th pct (ms)"),
        (axes[1], "ok_per_s", "Votes per second"),
    ]:
        ends = []
        for color, rows, label in [
            (SERIES[0], on_demand, "On-demand"),
            (SERIES[1], provisioned, "Provisioned, 20 WCU"),
        ]:
            values = pick(rows, "hot-room", "vote", field)
            xs = [n for n in counts if n in values]
            ys = [values[n] for n in xs]
            ax.plot(xs, ys, color=color, marker="o", markersize=6, label=label)
            if ys:
                ends.append((xs[-1], ys[-1]))
        ax.set_xticks(counts)
        ax.set_xlabel("Students (one room)")
        end_labels(ax, ends)
        ax.set_title(title)
    legend_below(fig, axes[0])
    return save(fig, "capacity-modes", out)


def live_latency(live_id: str, out: Path) -> Path:
    rows = [r for r in read(live_id, "live") if r["ok"] == "True"]
    fig, ax = plt.subplots(figsize=(8, 3))
    for color, op, label in [(SERIES[0], "post_idea", "Post idea"), (SERIES[1], "vote", "Vote")]:
        values = sorted(float(r["event_after_response_ms"]) for r in rows if r["op"] == op)
        if not values:
            continue
        share = [(i + 1) / len(values) * 100 for i in range(len(values))]
        ax.step(values, share, where="post", color=color, label=label)
    ax.set_title("Live update: HTTP response to WebSocket event")
    ax.set_xlabel("Milliseconds after the write returned")
    ax.set_ylabel("% of updates")
    ax.set_ylim(0, 100)
    ax.set_xlim(left=0)
    ax.grid(axis="x", visible=True)
    ax.legend(loc="lower right")
    return save(fig, "live-latency", out)


def main() -> int:
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="benchmark.py run id (default scenarios)")
    parser.add_argument("--provisioned-run", help="hot-room run on a provisioned table")
    parser.add_argument("--live-run", help="benchmark.py live run id")
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    RESULTS = args.results
    vote_latency(args.run, args.out)
    throughput(args.run, args.out)
    conflicts(args.run, args.out)
    query_vs_scan(args.run, args.out)
    if args.provisioned_run:
        capacity_modes(args.run, args.provisioned_run, args.out)
    if args.live_run:
        live_latency(args.live_run, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

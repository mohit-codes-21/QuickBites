#!/usr/bin/env python3
"""Generate performance-comparison figures from a QuickBites index benchmark JSON file.

Usage
-----
    python report/generate_figures.py ../logs/index_benchmark_XXXXXXXX.json

The script reads the JSON produced by ``app/benchmark_indexing.py`` (mode=full)
and writes three PNG charts into the ``figures/`` subdirectory (relative to this
script's location):

1. ``figures/sql_query_performance.png``   -- grouped horizontal bars (before/after p50)
2. ``figures/api_endpoint_performance.png`` -- same format for API response times
3. ``figures/sql_query_improvement.png``   -- percentage change per SQL query
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIGURES_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")


def _ensure_figures_dir() -> None:
    os.makedirs(FIGURES_DIR, exist_ok=True)


def _extract_sql_timings(data: dict) -> dict[str, dict[str, float]]:
    """Return {query_name: {"before": p50_ms, "after": p50_ms}}."""
    before_timings = data["before"]["queries"]["timings"]
    after_timings = data["after"]["queries"]["timings"]
    result: dict[str, dict[str, float]] = {}
    for name in sorted(before_timings.keys()):
        b = before_timings[name]["ms"]["p50"]
        a = after_timings.get(name, {}).get("ms", {}).get("p50", b)
        result[name] = {"before": b, "after": a}
    return result


def _extract_api_timings(data: dict) -> dict[str, dict[str, float]]:
    """Return {endpoint_name: {"before": p50_ms, "after": p50_ms}}."""
    before_timings = data["before"]["api"]["timings"]
    after_timings = data["after"]["api"]["timings"]
    result: dict[str, dict[str, float]] = {}
    for name in sorted(before_timings.keys()):
        b = before_timings[name]["timing"]["ms"]["p50"]
        a = after_timings.get(name, {}).get("timing", {}).get("ms", {}).get("p50", b)
        result[name] = {"before": b, "after": a}
    return result


def _extract_explain_changes(data: dict) -> list[dict]:
    """Return a list of dicts summarising first-row EXPLAIN changes per query."""
    before_explains = data["before"]["queries"]["explain"]
    after_explains = data["after"]["queries"]["explain"]
    rows: list[dict] = []
    for name in sorted(before_explains.keys()):
        brows = before_explains[name]
        arows = after_explains.get(name, [])
        b0 = brows[0] if brows else {}
        a0 = arows[0] if arows else {}
        rows.append({
            "query": name,
            "before_type": b0.get("type", ""),
            "after_type": a0.get("type", ""),
            "before_key": b0.get("key") or "(none)",
            "after_key": a0.get("key") or "(none)",
            "before_extra": b0.get("Extra") or "",
            "after_extra": a0.get("Extra") or "",
        })
    return rows


# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------

def chart_sql_performance(timings: dict[str, dict[str, float]]) -> str:
    """Grouped horizontal bar chart: before vs after p50 for SQL queries."""
    names = list(timings.keys())
    before_vals = [timings[n]["before"] for n in names]
    after_vals = [timings[n]["after"] for n in names]
    n = len(names)

    fig_height = max(4, n * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(10, fig_height))

    bar_height = 0.35
    y_positions = list(range(n))
    y_before = [y + bar_height / 2 for y in y_positions]
    y_after = [y - bar_height / 2 for y in y_positions]

    ax.barh(y_before, before_vals, height=bar_height, label="Before Indexing",
            color="#E8755A", edgecolor="white", linewidth=0.5)
    ax.barh(y_after, after_vals, height=bar_height, label="After Indexing",
            color="#2BA89E", edgecolor="white", linewidth=0.5)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("p50 Execution Time (ms)", fontsize=10)
    ax.set_title("SQL Query Performance: Before vs After Indexing (p50, ms)", fontsize=12, pad=12)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    path = os.path.join(FIGURES_DIR, "sql_query_performance.png")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def chart_api_performance(timings: dict[str, dict[str, float]]) -> str:
    """Grouped horizontal bar chart: before vs after p50 for API endpoints."""
    names = list(timings.keys())
    before_vals = [timings[n]["before"] for n in names]
    after_vals = [timings[n]["after"] for n in names]
    n = len(names)

    fig_height = max(4, n * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(10, fig_height))

    bar_height = 0.35
    y_positions = list(range(n))
    y_before = [y + bar_height / 2 for y in y_positions]
    y_after = [y - bar_height / 2 for y in y_positions]

    ax.barh(y_before, before_vals, height=bar_height, label="Before Indexing",
            color="#E8755A", edgecolor="white", linewidth=0.5)
    ax.barh(y_after, after_vals, height=bar_height, label="After Indexing",
            color="#2BA89E", edgecolor="white", linewidth=0.5)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("p50 Response Time (ms)", fontsize=10)
    ax.set_title("API Endpoint Performance: Before vs After Indexing (p50, ms)", fontsize=12, pad=12)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    path = os.path.join(FIGURES_DIR, "api_endpoint_performance.png")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


def chart_sql_improvement(timings: dict[str, dict[str, float]]) -> str:
    """Bar chart showing percentage change (improvement / regression) per query."""
    names = list(timings.keys())
    pct_changes: list[float] = []
    for n in names:
        b = timings[n]["before"]
        a = timings[n]["after"]
        if b == 0:
            pct_changes.append(0.0)
        else:
            pct_changes.append(((b - a) / b) * 100.0)

    colors = ["#2BA89E" if p >= 0 else "#E8755A" for p in pct_changes]

    n_queries = len(names)
    fig_height = max(4, n_queries * 0.5 + 1.5)
    fig, ax = plt.subplots(figsize=(10, fig_height))

    y_positions = list(range(n_queries))
    ax.barh(y_positions, pct_changes, color=colors, edgecolor="white", linewidth=0.5)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Change in p50 Execution Time (%)", fontsize=10)
    ax.set_title("Query Execution Time Change (%)", fontsize=12, pad=12)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Annotate bars with percentage values
    for i, pct in enumerate(pct_changes):
        ha = "left" if pct >= 0 else "right"
        offset = 0.5 if pct >= 0 else -0.5
        ax.text(pct + offset, i, f"{pct:+.1f}%", va="center", ha=ha, fontsize=8)

    path = os.path.join(FIGURES_DIR, "sql_query_improvement.png")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Stdout summaries
# ---------------------------------------------------------------------------

def print_explain_summary(explain_rows: list[dict]) -> None:
    """Print a table comparing EXPLAIN key and Extra before/after."""
    hdr = f"{'Query':<35} {'Before Key':<20} {'After Key':<40} {'Before Extra':<35} {'After Extra':<35}"
    print("\n" + "=" * len(hdr))
    print("EXPLAIN Plan Changes (first row of each query)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in explain_rows:
        print(
            f"{r['query']:<35} "
            f"{r['before_key']:<20} "
            f"{r['after_key']:<40} "
            f"{r['before_extra']:<35} "
            f"{r['after_extra']:<35}"
        )
    print()


def print_timing_summary(sql_timings: dict[str, dict[str, float]],
                          api_timings: dict[str, dict[str, float]]) -> None:
    """Print a summary of timing improvements / regressions."""
    print("=" * 80)
    print("SQL Query Timing Summary (p50, ms)")
    print("=" * 80)
    hdr = f"{'Query':<35} {'Before':<12} {'After':<12} {'Change':<12}"
    print(hdr)
    print("-" * 71)
    for name, vals in sql_timings.items():
        b, a = vals["before"], vals["after"]
        if b == 0:
            pct_str = "N/A"
        else:
            pct = ((b - a) / b) * 100.0
            pct_str = f"{pct:+.1f}%"
        print(f"{name:<35} {b:<12.4f} {a:<12.4f} {pct_str:<12}")

    improved = sum(1 for v in sql_timings.values() if v["after"] < v["before"])
    regressed = sum(1 for v in sql_timings.values() if v["after"] > v["before"])
    unchanged = len(sql_timings) - improved - regressed
    print(f"\nImproved: {improved}  |  Regressed: {regressed}  |  Unchanged: {unchanged}")

    print()
    print("=" * 80)
    print("API Endpoint Timing Summary (p50, ms)")
    print("=" * 80)
    hdr = f"{'Endpoint':<35} {'Before':<12} {'After':<12} {'Change':<12}"
    print(hdr)
    print("-" * 71)
    for name, vals in api_timings.items():
        b, a = vals["before"], vals["after"]
        if b == 0:
            pct_str = "N/A"
        else:
            pct = ((b - a) / b) * 100.0
            pct_str = f"{pct:+.1f}%"
        print(f"{name:<35} {b:<12.4f} {a:<12.4f} {pct_str:<12}")

    improved = sum(1 for v in api_timings.values() if v["after"] < v["before"])
    regressed = sum(1 for v in api_timings.values() if v["after"] > v["before"])
    unchanged = len(api_timings) - improved - regressed
    print(f"\nImproved: {improved}  |  Regressed: {regressed}  |  Unchanged: {unchanged}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate performance-comparison figures from a QuickBites index benchmark JSON file."
    )
    parser.add_argument(
        "json_file",
        help="Path to the benchmark JSON file produced by benchmark_indexing.py (mode=full)",
    )
    args = parser.parse_args()

    json_path = os.path.abspath(args.json_file)
    if not os.path.isfile(json_path):
        print(f"ERROR: File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate required sections
    for section in ("before", "after"):
        if section not in data:
            print(f"ERROR: JSON is missing '{section}' section. "
                  f"Run benchmark_indexing.py with --mode full.", file=sys.stderr)
            sys.exit(1)

    _ensure_figures_dir()

    # Extract data
    sql_timings = _extract_sql_timings(data)
    api_timings = _extract_api_timings(data)
    explain_rows = _extract_explain_changes(data)

    # Generate charts
    p1 = chart_sql_performance(sql_timings)
    print(f"[OK] {p1}")

    p2 = chart_api_performance(api_timings)
    print(f"[OK] {p2}")

    p3 = chart_sql_improvement(sql_timings)
    print(f"[OK] {p3}")

    # Print summaries to stdout
    print_explain_summary(explain_rows)
    print_timing_summary(sql_timings, api_timings)


if __name__ == "__main__":
    main()

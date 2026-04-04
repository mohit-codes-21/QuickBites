#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
FIG_DIR = os.path.join(BASE_DIR, "figures", "test_cases")

METRICS_JSONL = os.path.join(LOG_DIR, "test_metrics.jsonl")
STRESS_CSV = os.path.join(LOG_DIR, "stress_results.csv")
LATEST_CSV = os.path.join(LOG_DIR, "test_case_metrics_latest.csv")
SUMMARY_JSON = os.path.join(LOG_DIR, "test_case_metrics_summary.json")
LOCUST_STATS_CSV = os.path.join(LOG_DIR, "locust_latest_stats.csv")
LOCUST_OUTPUT_LOG = os.path.join(LOG_DIR, "locust_latest_output.txt")


def _ensure_dirs() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(FIG_DIR, exist_ok=True)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _parse_reason_metrics(reason: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in re.findall(r"([a-zA-Z_]+)=([^,]+)", reason or ""):
        out[key.strip()] = value.strip()
    return out


def _extract_fraction_total(reason: str, key: str) -> int:
    match = re.search(rf"{re.escape(key)}=(\d+)/(\d+)", reason or "")
    return _safe_int(match.group(2), 0) if match else 0


def _find_latest_row(latest_rows: list[dict], test_name: str) -> dict:
    for row in latest_rows:
        if row.get("testName") == test_name:
            return row
    return {}


def _load_locust_rows() -> list[dict]:
    if not os.path.isfile(LOCUST_STATS_CSV):
        return []

    rows = []
    with open(LOCUST_STATS_CSV, "r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        rows.extend(reader)
    return rows


def _load_locust_user_count() -> int:
    if not os.path.isfile(LOCUST_OUTPUT_LOG):
        return 0

    with open(LOCUST_OUTPUT_LOG, "r", encoding="utf-8") as fp:
        text = fp.read()

    match = re.search(r"\((\d+) total users\)", text)
    if match:
        return _safe_int(match.group(1), 0)
    return 0


def _load_metrics_entries() -> list[dict]:
    if not os.path.isfile(METRICS_JSONL):
        return []

    rows = []
    with open(METRICS_JSONL, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(row)
    return rows


def _latest_by_test(entries: list[dict]) -> list[dict]:
    latest = {}
    for row in entries:
        key = row.get("testName", "")
        if key:
            latest[key] = row
    return list(latest.values())


def _write_latest_csv(latest_rows: list[dict]) -> None:
    with open(LATEST_CSV, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["test_name", "suite", "status", "duration_ms", "reason"])
        for row in sorted(latest_rows, key=lambda x: (x.get("suite", ""), x.get("testName", ""))):
            writer.writerow(
                [
                    row.get("testName", ""),
                    row.get("suite", ""),
                    row.get("status", ""),
                    row.get("durationMs", ""),
                    row.get("reason", ""),
                ]
            )


def _plot_pass_fail_by_suite(latest_rows: list[dict]) -> str:
    suite_stats = defaultdict(lambda: {"PASS": 0, "FAIL": 0})
    for row in latest_rows:
        suite = row.get("suite", "unspecified")
        status = row.get("status", "FAIL")
        if status not in {"PASS", "FAIL"}:
            status = "FAIL"
        suite_stats[suite][status] += 1

    suites = sorted(suite_stats.keys())
    pass_counts = [suite_stats[s]["PASS"] for s in suites]
    fail_counts = [suite_stats[s]["FAIL"] for s in suites]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = list(range(len(suites)))
    ax.bar(x, pass_counts, color="#2BA89E", label="PASS")
    ax.bar(x, fail_counts, bottom=pass_counts, color="#E8755A", label="FAIL")

    ax.set_xticks(x)
    ax.set_xticklabels(suites, rotation=20, ha="right")
    ax.set_ylabel("Test Count")
    ax.set_title("Latest Test Results by Suite (PASS/FAIL)")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    for i, suite in enumerate(suites):
        total = pass_counts[i] + fail_counts[i]
        pass_rate = (pass_counts[i] / total * 100.0) if total else 0.0
        ax.text(i, total + 0.08, f"{pass_counts[i]}/{total} ({pass_rate:.0f}%)", ha="center", va="bottom", fontsize=8)

    path = os.path.join(FIG_DIR, "test_pass_fail_by_suite.png")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def _plot_scenario_scale_and_creation(latest_rows: list[dict]) -> str:
    c1 = _find_latest_row(latest_rows, "Concurrent Scenario 1 - 15 parallel reads")
    c2 = _find_latest_row(latest_rows, "Concurrent Scenario 2 - 15 parallel updates")
    c3 = _find_latest_row(latest_rows, "Concurrent Scenario 3 - delete while readers run")
    c4 = _find_latest_row(latest_rows, "Concurrent Scenario 4 - same cart item contention")
    r1 = _find_latest_row(latest_rows, "Race Condition - 50 concurrent signup attempts")
    r2 = _find_latest_row(latest_rows, "Race Condition - concurrent delivery acceptance")
    stress = _find_latest_row(latest_rows, "Stress Test (threading fallback)")

    c1_total = _extract_fraction_total(c1.get("reason", ""), "successful_reads")
    c2_total = _extract_fraction_total(c2.get("reason", ""), "updates_ok")
    c3_metrics = _parse_reason_metrics(c3.get("reason", ""))
    c3_total = _safe_int(c3_metrics.get("readers"), 0) + 1 if c3_metrics else 0
    c4_total = _extract_fraction_total(c4.get("reason", ""), "updates_ok")

    r1_metrics = _parse_reason_metrics(r1.get("reason", ""))
    r1_success = _safe_int(r1_metrics.get("success"), 0)
    r1_rolled_back = _safe_int(r1_metrics.get("rolled_back"), 0)
    r1_total = r1_success + r1_rolled_back

    r2_metrics = _parse_reason_metrics(r2.get("reason", ""))
    r2_contenders = _safe_int(r2_metrics.get("contenders"), 0)
    r2_success = _safe_int(r2_metrics.get("success"), 0)

    stress_metrics = _parse_reason_metrics(stress.get("reason", ""))
    stress_total = _safe_int(stress_metrics.get("total"), 0)
    stress_cleaned = _safe_int(stress_metrics.get("cleaned"), 0)

    locust_rows = _load_locust_rows()
    locust_users = _load_locust_user_count()
    locust_total_requests = 0
    locust_login_requests = 0
    for row in locust_rows:
        name = row.get("Name", "")
        if name == "Aggregated":
            locust_total_requests = _safe_int(row.get("Request Count"), 0)
        if name == "POST /api/auth/login":
            locust_login_requests = _safe_int(row.get("Request Count"), 0)

    scenario_labels = [
        "C1 parallel reads",
        "C2 parallel updates",
        "C3 readers + delete",
        "C4 cart contention",
        "Race signup attempts",
        "Race delivery contenders",
        "Stress script requests",
        "Locust users",
        "Locust total requests",
    ]
    scenario_counts = [
        c1_total,
        c2_total,
        c3_total,
        c4_total,
        r1_total,
        r2_contenders,
        stress_total,
        locust_users,
        locust_total_requests,
    ]

    entity_labels = [
        "Race users created",
        "Race users rolled back",
        "Delivery assignments won",
        "Stress temp items cleaned",
        "Locust login sessions",
    ]
    entity_counts = [
        r1_success,
        r1_rolled_back,
        r2_success,
        stress_cleaned,
        locust_login_requests,
    ]

    fig, axes = plt.subplots(2, 1, figsize=(12, 8.5), gridspec_kw={"height_ratios": [3, 2]})

    y_top = list(range(len(scenario_labels)))
    axes[0].barh(y_top, scenario_counts, color="#4C78A8")
    axes[0].set_yticks(y_top)
    axes[0].set_yticklabels(scenario_labels, fontsize=9)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Participants / Requests")
    axes[0].set_title("Scenario Load Scale (Who/How Many Participated)")
    axes[0].grid(axis="x", linestyle="--", alpha=0.35)
    for i, val in enumerate(scenario_counts):
        axes[0].text(val + max(1, 0.01 * max(scenario_counts or [1])), i, str(val), va="center", fontsize=8)

    y_bottom = list(range(len(entity_labels)))
    axes[1].barh(y_bottom, entity_counts, color=["#2BA89E", "#E8755A", "#2BA89E", "#F2CF5B", "#72B7B2"])
    axes[1].set_yticks(y_bottom)
    axes[1].set_yticklabels(entity_labels, fontsize=9)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Entity Count")
    axes[1].set_title("Created / Rolled Back Entities by Scenario")
    axes[1].grid(axis="x", linestyle="--", alpha=0.35)
    for i, val in enumerate(entity_counts):
        axes[1].text(val + max(1, 0.02 * max(entity_counts or [1])), i, str(val), va="center", fontsize=8)

    path = os.path.join(FIG_DIR, "test_duration_by_case_ms.png")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def _plot_stress_endpoint_metrics() -> str | None:
    if not os.path.isfile(STRESS_CSV):
        return None

    threading_rows = []
    with open(STRESS_CSV, "r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        threading_rows.extend(reader)

    locust_rows = _load_locust_rows()
    locust_map = {
        row.get("Name", ""): row
        for row in locust_rows
        if row.get("Name") and row.get("Name") not in {"Aggregated", "POST /api/auth/login"}
    }

    endpoints = [row.get("endpoint", "") for row in threading_rows]
    thread_avg = [_safe_float(row.get("avg_response_ms"), 0.0) for row in threading_rows]
    thread_p95 = [_safe_float(row.get("p95_response_ms"), 0.0) for row in threading_rows]
    locust_avg = [_safe_float((locust_map.get(ep) or {}).get("Average Response Time"), 0.0) for ep in endpoints]
    locust_p95 = [_safe_float((locust_map.get(ep) or {}).get("95%"), 0.0) for ep in endpoints]

    x = list(range(len(endpoints)))
    width = 0.38
    fig, axes = plt.subplots(2, 1, figsize=(12, 8.2), sharex=True)

    axes[0].bar([i - width / 2 for i in x], thread_avg, width=width, color="#4C78A8", label="Threading avg")
    axes[0].bar([i + width / 2 for i in x], locust_avg, width=width, color="#72B7B2", label="Locust avg")
    axes[0].set_ylabel("Avg Latency (ms)")
    axes[0].set_title("Endpoint Average Latency: Threading vs Locust")
    axes[0].legend()
    axes[0].grid(axis="y", linestyle="--", alpha=0.35)

    axes[1].bar([i - width / 2 for i in x], thread_p95, width=width, color="#F58518", label="Threading p95")
    axes[1].bar([i + width / 2 for i in x], locust_p95, width=width, color="#E45756", label="Locust p95")
    axes[1].set_ylabel("P95 Latency (ms)")
    axes[1].set_title("Endpoint P95 Latency: Threading vs Locust")
    axes[1].legend()
    axes[1].grid(axis="y", linestyle="--", alpha=0.35)

    axes[1].set_xticks(x)
    axes[1].set_xticklabels(endpoints, rotation=20, ha="right")

    path = os.path.join(FIG_DIR, "stress_endpoint_metrics.png")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


def _write_summary(latest_rows: list[dict], generated_paths: list[str]) -> None:
    suite_totals = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    for row in latest_rows:
        suite = row.get("suite", "unspecified")
        suite_totals[suite]["total"] += 1
        if row.get("passed", False):
            suite_totals[suite]["passed"] += 1
        else:
            suite_totals[suite]["failed"] += 1

    payload = {
        "metricsSource": os.path.relpath(METRICS_JSONL, BASE_DIR),
        "latestEntryCount": len(latest_rows),
        "suiteTotals": suite_totals,
        "generatedFigures": [os.path.relpath(path, BASE_DIR) for path in generated_paths],
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def main() -> None:
    _ensure_dirs()
    entries = _load_metrics_entries()
    if not entries:
        raise SystemExit(f"No metrics found at {METRICS_JSONL}. Run tests first.")

    latest_rows = _latest_by_test(entries)
    _write_latest_csv(latest_rows)

    generated = []
    generated.append(_plot_pass_fail_by_suite(latest_rows))
    generated.append(_plot_scenario_scale_and_creation(latest_rows))

    stress_plot = _plot_stress_endpoint_metrics()
    if stress_plot:
        generated.append(stress_plot)

    _write_summary(latest_rows, generated)

    print("Generated files:")
    print(f"- {os.path.relpath(LATEST_CSV, BASE_DIR)}")
    print(f"- {os.path.relpath(SUMMARY_JSON, BASE_DIR)}")
    for path in generated:
        print(f"- {os.path.relpath(path, BASE_DIR)}")


if __name__ == "__main__":
    main()

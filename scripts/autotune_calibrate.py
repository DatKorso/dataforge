#!/usr/bin/env python3
"""
One-off calibration script: probe `search_matches` performance on a sample of wb_sku
and recommend batch_size, limit_per_input and parallel_workers.

This script is standalone and can be removed after calibration.
"""
from __future__ import annotations

import statistics
import time
from typing import Iterable

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `dataforge` package can be imported when run as a script
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dataforge.db import get_connection
from dataforge.matching import search_matches
from dataforge.secrets import load_secrets


def time_query(values: list[str], md_token: str | None, md_database: str | None, limit: int | None = 5) -> tuple[float, int]:
    """Run search_matches for given values and return (elapsed_seconds, rows_returned)."""
    t0 = time.perf_counter()
    df = search_matches(values, input_type="wb_sku", limit_per_input=limit, md_token=md_token, md_database=md_database)
    t1 = time.perf_counter()
    return (t1 - t0), (len(df) if df is not None else 0)


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Simple linear regression (least squares) returning intercept, slope for y = intercept + slope*x"""
    if len(xs) < 2:
        return 0.0, ys[0] if ys else 0.0
    xbar = statistics.mean(xs)
    ybar = statistics.mean(ys)
    num = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    den = sum((x - xbar) ** 2 for x in xs)
    slope = num / den if den != 0 else 0.0
    intercept = ybar - slope * xbar
    return intercept, slope


def recommend_params(intercept: float, slope: float, avg_rows_per_input: float, target_latency: float = 6.0) -> dict:
    min_batch = 10
    max_batch = 1000
    est_batch = int(max(min_batch, min(max_batch, (target_latency - intercept) / slope if slope > 0 else max_batch)))
    if est_batch < 1:
        est_batch = min_batch

    # limit_per_input heuristic
    if avg_rows_per_input > 10:
        limit = 5
    else:
        limit = min(10, max(1, int(round(avg_rows_per_input) + 1)))

    # parallel workers heuristic (conservative)
    workers = 2 if est_batch >= 32 else 1
    return {"batch_size": est_batch, "limit_per_input": limit, "parallel_workers": workers}


def run_probe(sample: list[str], md_token: str | None, md_database: str | None, *,
              probe_sizes=(8, 32, 128), repeats: int = 3, target_latency: float = 6.0):
    probe_sizes = [p for p in probe_sizes if p <= len(sample)]
    if not probe_sizes:
        raise ValueError("Sample too small for probe sizes")

    # Warm-up: run one small query to warm DB/caches
    print("Warm-up query...")
    try:
        _ = time_query(sample[: min(8, len(sample))], md_token, md_database, limit=5)
    except Exception as exc:  # noqa: BLE001
        print("Warm-up failed:", exc)

    import statistics as _stats

    median_times = []
    median_rows = []
    diagnostics: dict[int, dict] = {}

    for p in probe_sizes:
        times = []
        rows = []
        for i in range(repeats):
            # rotate window to vary inputs
            start = (i * p) % len(sample)
            batch = [sample[(start + j) % len(sample)] for j in range(p)]
            try:
                t, r = time_query(batch, md_token, md_database, limit=5)
            except Exception as exc:  # noqa: BLE001
                print(f"probe_size={p} run {i+1} failed: {exc}")
                t, r = float('inf'), 0
            print(f"probe_size={p} run {i+1}: time={t:.3f}s, rows={r}")
            times.append(t)
            rows.append(r)

        med_t = float(_stats.median(times))
        med_r = int(_stats.median(rows))
        median_times.append(med_t)
        median_rows.append(med_r)
        diagnostics[p] = {"times": times, "rows": rows, "median_time": med_t, "median_rows": med_r}

    intercept, slope = linear_fit([float(x) for x in probe_sizes], median_times)

    # avg_rows_per_input: median_rows_total / total_probe_size
    total_probe = sum(probe_sizes)
    total_rows = sum(median_rows)
    avg_rows_per_input = (total_rows / total_probe) if total_probe else 0.0

    # safe recommendations with memory checks
    rec = recommend_params(intercept, slope, avg_rows_per_input, target_latency=target_latency)

    # memory estimate (conservative)
    avg_row_bytes = 1500  # conservative estimate per returned row
    mem_est_bytes = rec["batch_size"] * avg_rows_per_input * avg_row_bytes
    mem_mb = mem_est_bytes / (1024 * 1024)
    if mem_mb > 200:  # safety cap: 200 MB
        # reduce batch size
        factor = 200.0 / mem_mb
        old = rec["batch_size"]
        rec["batch_size"] = max(10, int(old * factor))

    print("\nDiagnostics per probe size:")
    for p in probe_sizes:
        d = diagnostics[p]
        print(f" size={p}: median_time={d['median_time']:.3f}s median_rows={d['median_rows']} runs={d['times']}")

    print("\nCalibration summary:")
    print(f"intercept (base_overhead) = {intercept:.3f}s")
    print(f"slope (latency_per_item) = {slope:.6f}s/item")
    print(f"avg_rows_per_input = {avg_rows_per_input:.3f}")
    print(f"estimated memory per batch ~ {mem_mb:.1f} MB (batch_size={rec['batch_size']})")
    print("recommended:")
    for k, v in rec.items():
        print(f"  {k}: {v}")
    return {"recommendation": rec, "diagnostics": diagnostics}


def main():
    secrets = load_secrets()
    md_token = secrets.get("md_token")
    md_database = secrets.get("md_database")
    import argparse

    parser = argparse.ArgumentParser(description="Autotune calibration for search_matches")
    parser.add_argument("--input-file", help="Path to newline-separated wb_sku file (optional)")
    parser.add_argument("--target-latency", type=float, default=6.0, help="Target latency in seconds")
    args = parser.parse_args()

    # list of wb_sku: default embedded sample (50). You can provide a full list via --input-file
    sample_input = [
        113259445, 507852379, 250464885, 119357544, 418779297, 418786685, 241725949, 171745338, 168567724, 418786702,
        171743578, 418779343, 171744204, 418786740, 171744272, 520961469, 418779413, 418779392, 418779394, 260880231,
        242266205, 171745221, 418779337, 163509547, 171744138, 119357619, 241725929, 241725932, 163509480, 241725951,
        418779271, 418779331, 119225892, 119225890, 171743957, 250464881, 418779372, 171743729, 418779265, 235211468,
        168568971, 242266203, 520970201, 418779329, 241725937, 171744195, 418779299, 168567683, 418786746, 418786811,
    ]

    if args.input_file:
        p = Path(args.input_file)
        if not p.exists():
            print(f"Input file {args.input_file} not found. Using embedded sample of {len(sample_input)} items.")
        else:
            with p.open("r", encoding="utf8") as fh:
                lines = [l.strip() for l in fh if l.strip()]
            sample_input = []
            for l in lines:
                try:
                    sample_input.append(str(int(l)))
                except Exception:
                    # ignore malformed lines
                    pass

    # normalize to strings and ensure we have at least one
    sample_input = [str(x) for x in sample_input]
    print(f"Running calibration with sample size = {len(sample_input)}")
    rec = run_probe(sample_input, md_token, md_database, target_latency=args.target_latency)
    print("Done")


if __name__ == "__main__":
    main()

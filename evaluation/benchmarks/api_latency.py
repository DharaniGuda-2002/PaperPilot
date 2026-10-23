"""API read latency against a running stack (stdlib only).

For each endpoint: warm-up requests, then N timed requests at concurrency 1
and at concurrency C (thread pool). Reports p50/p95/p99 in milliseconds,
throughput, response size, and any non-200 responses. Rate-limited
endpoints (create, search) are excluded on purpose: the limiter, not the
server, would set their numbers.

Usage:
  python evaluation/benchmarks/api_latency.py --base http://localhost:8000 \
      --investigation <id with a report> [--requests 200] [--concurrency 8]
"""

import argparse
import json
import platform
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


def fetch(url: str) -> tuple[float, int, int]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        body, status = error.read(), error.code
    return (time.perf_counter() - started) * 1000, status, len(body)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(q * (len(ordered) - 1)))
    return round(ordered[index], 1)


def measure(url: str, requests: int, concurrency: int) -> dict[str, object]:
    for _ in range(10):
        fetch(url)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(fetch, [url] * requests))
    elapsed = time.perf_counter() - started
    latencies = [r[0] for r in results]
    return {
        "concurrency": concurrency,
        "requests": requests,
        "non_200": sum(1 for r in results if r[1] != 200),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "mean_ms": round(statistics.fmean(latencies), 1),
        "throughput_rps": round(requests / elapsed, 1),
        "bytes": results[-1][2],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--investigation", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--out", type=Path, default=Path("evaluation/benchmarks/results"))
    args = parser.parse_args()

    base, inv = args.base.rstrip("/"), args.investigation
    with urllib.request.urlopen(f"{base}/api/v1/investigations/{inv}/evidence", timeout=30) as r:
        evidence = json.load(r)
    items = evidence["items"] if isinstance(evidence, dict) else evidence
    evidence_id = next(e["id"] for e in items if e.get("passage"))

    endpoints = {
        "health/ready": "/health/ready",
        "investigations (list 20)": "/api/v1/investigations?limit=20",
        "investigation": f"/api/v1/investigations/{inv}",
        "papers (25)": f"/api/v1/investigations/{inv}/papers?limit=25",
        "evidence (all)": f"/api/v1/investigations/{inv}/evidence",
        "report": f"/api/v1/investigations/{inv}/report",
        "evidence detail": f"/api/v1/evidence/{evidence_id}",
    }
    rows = []
    for name, path in endpoints.items():
        for concurrency in (1, args.concurrency):
            row = {"endpoint": name, **measure(base + path, args.requests, concurrency)}
            rows.append(row)
            print(
                f"{name:<26} c={row['concurrency']:<2} p50={row['p50_ms']:>7} "
                f"p95={row['p95_ms']:>7} p99={row['p99_ms']:>7} ms  "
                f"{row['throughput_rps']:>6} req/s  {row['bytes']:>7} B  non-200={row['non_200']}"
            )

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = args.out / f"{stamp}-api-latency.json"
    out.write_text(
        json.dumps(
            {
                "run_at": stamp,
                "base": base,
                "machine": f"{platform.system()} {platform.machine()}",
                "results": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

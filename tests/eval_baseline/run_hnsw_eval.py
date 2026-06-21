#!/usr/bin/env python3
"""Benchmark Qdrant HNSW against exact dense search using existing filing vectors."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE_COLLECTION = "filings"
BENCHMARK_COLLECTION = "filings_hnsw_benchmark"
RESULTS_DIR = Path(__file__).parent / "results"


def request(method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} failed ({exc.code}): {detail}") from exc


def scroll_vectors(base_url: str) -> list[dict]:
    points: list[dict] = []
    offset = None
    while True:
        payload = {
            "limit": 256,
            "with_payload": False,
            "with_vector": ["text-dense"],
        }
        if offset is not None:
            payload["offset"] = offset
        data = request(
            "POST",
            f"{base_url}/collections/{SOURCE_COLLECTION}/points/scroll",
            payload,
        )["result"]
        points.extend(data["points"])
        offset = data.get("next_page_offset")
        if offset is None:
            break
    return points


def create_benchmark_collection(base_url: str, dimension: int) -> None:
    try:
        request("DELETE", f"{base_url}/collections/{BENCHMARK_COLLECTION}")
    except RuntimeError:
        pass
    request(
        "PUT",
        f"{base_url}/collections/{BENCHMARK_COLLECTION}",
        {
            "vectors": {"size": dimension, "distance": "Cosine"},
            "hnsw_config": {
                "m": 16,
                "ef_construct": 100,
                "full_scan_threshold": 10,
            },
            "optimizers_config": {"indexing_threshold": 1},
        },
    )


def upsert_vectors(base_url: str, points: list[dict]) -> None:
    request(
        "PUT",
        f"{base_url}/collections/{BENCHMARK_COLLECTION}/points?wait=true",
        {
            "points": [
                {"id": point["id"], "vector": point["vector"]["text-dense"]}
                for point in points
            ]
        },
    )


def wait_for_index(base_url: str, expected: int) -> dict:
    deadline = time.time() + 60
    last = {}
    while time.time() < deadline:
        last = request("GET", f"{base_url}/collections/{BENCHMARK_COLLECTION}")["result"]
        if last.get("indexed_vectors_count", 0) >= expected and last.get("status") == "green":
            return last
        time.sleep(0.5)
    raise RuntimeError(
        "Qdrant did not build the HNSW index within 60 seconds "
        f"(indexed={last.get('indexed_vectors_count', 0)}, expected={expected})"
    )


def perturb(vector: list[float], rng: random.Random, noise: float = 0.01) -> list[float]:
    changed = [value + rng.gauss(0, noise) for value in vector]
    norm = math.sqrt(sum(value * value for value in changed)) or 1.0
    return [value / norm for value in changed]


def query(base_url: str, vector: list[float], top_k: int, params: dict) -> tuple[list[str], float]:
    started = time.perf_counter()
    result = request(
        "POST",
        f"{base_url}/collections/{BENCHMARK_COLLECTION}/points/query",
        {
            "query": vector,
            "limit": top_k,
            "params": params,
            "with_payload": False,
            "with_vector": False,
        },
    )["result"]["points"]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return [str(point["id"]) for point in result], elapsed_ms


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def evaluate(base_url: str, points: list[dict], query_count: int, top_k: int) -> dict:
    rng = random.Random(42)
    sampled = rng.sample(points, min(query_count, len(points)))
    queries = [perturb(point["vector"]["text-dense"], rng) for point in sampled]

    exact_results = []
    exact_latencies = []
    for vector in queries:
        ids, latency = query(base_url, vector, top_k, {"exact": True})
        exact_results.append(ids)
        exact_latencies.append(latency)

    configurations = {}
    for ef in (8, 16, 32, 64, 128):
        recalls = []
        latencies = []
        for vector, expected in zip(queries, exact_results):
            actual, latency = query(
                base_url,
                vector,
                top_k,
                {"exact": False, "hnsw_ef": ef},
            )
            recalls.append(len(set(actual) & set(expected)) / top_k)
            latencies.append(latency)
        configurations[str(ef)] = {
            f"recall_at_{top_k}": round(statistics.mean(recalls), 4),
            "latency_mean_ms": round(statistics.mean(latencies), 3),
            "latency_p50_ms": round(statistics.median(latencies), 3),
            "latency_p95_ms": round(percentile(latencies, 0.95), 3),
        }

    return {
        "vector_count": len(points),
        "query_count": len(queries),
        "dimension": len(points[0]["vector"]["text-dense"]),
        "top_k": top_k,
        "exact": {
            "latency_mean_ms": round(statistics.mean(exact_latencies), 3),
            "latency_p50_ms": round(statistics.median(exact_latencies), 3),
            "latency_p95_ms": round(percentile(exact_latencies, 0.95), 3),
        },
        "hnsw": configurations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:6333")
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    points = scroll_vectors(args.url)
    if not points:
        raise SystemExit("No dense vectors found in the filings collection")

    create_benchmark_collection(args.url, len(points[0]["vector"]["text-dense"]))
    try:
        upsert_vectors(args.url, points)
        collection = wait_for_index(args.url, len(points))
        results = evaluate(args.url, points, args.queries, args.top_k)
        results["indexed_vectors_count"] = collection.get("indexed_vectors_count", 0)
        results["timestamp"] = datetime.now(timezone.utc).isoformat()

        RESULTS_DIR.mkdir(exist_ok=True)
        output = RESULTS_DIR / "hnsw_eval_latest.json"
        output.write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
        print(f"\nSaved: {output}")
    finally:
        request("DELETE", f"{args.url}/collections/{BENCHMARK_COLLECTION}")


if __name__ == "__main__":
    main()

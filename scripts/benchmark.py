"""Run from repository root: PYTHONPATH=backend backend/.venv/bin/python scripts/benchmark.py."""

import json, platform, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import numpy as np
from app.demo import make_demo
from app.models import SimulationInput
from app.engine import simulate

network = make_demo()
request = SimulationInput(
    network_version=network.version,
    incident={"type": "pipe_break", "segment_id": "S-PIPE-0-1"},
)
samples = []
for i in range(20):
    start = time.perf_counter()
    result = simulate(network, request)
    samples.append((time.perf_counter() - start) * 1000)
with ThreadPoolExecutor(max_workers=10) as pool:
    started = time.perf_counter()
    results = list(pool.map(lambda _: simulate(network, request), range(10)))
    concurrent_ms = (time.perf_counter() - started) * 1000
report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "platform": platform.platform(),
    "processor": platform.processor(),
    "python": platform.python_version(),
    "nodes": len(network.nodes),
    "pipes": len(network.pipes),
    "consumers": len(network.consumers),
    "runs": len(samples),
    "p95_ms": round(float(np.percentile(samples, 95)), 2),
    "max_ms": round(max(samples), 2),
    "concurrent_requests": 10,
    "concurrent_batch_ms": round(concurrent_ms, 2),
    "passed": float(np.percentile(samples, 95)) <= 10000,
    "samples_ms": [round(x, 2) for x in samples],
    "note": "Kernel benchmark. Concurrent batch is threads in one process, not HTTP p95.",
}
with open("docs/kpi-report.json", "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(json.dumps(report, indent=2, ensure_ascii=False))

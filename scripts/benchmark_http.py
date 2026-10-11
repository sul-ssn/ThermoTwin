import asyncio, json, platform, time
from datetime import datetime, timezone
import httpx
import numpy as np


async def main():
    async with httpx.AsyncClient(
        base_url="http://localhost:8000/api/v1", timeout=30
    ) as client:
        response = await client.post(
            "/auth/login",
            json={"username": "dispatcher", "password": "demo-dispatcher"},
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["token"]
        response = await client.get("/network")
        response.raise_for_status()
        network = response.json()
        data = {
            "network_version": network["version"],
            "incident": {
                "type": "pipe_break",
                "segment_id": next(p["id"] for p in network["pipes"] if p["contour"] == "supply" and not p["backup"]),
            },
        }

        async def run():
            t = time.perf_counter()
            r = await client.post("/simulations", json=data)
            r.raise_for_status()
            return (time.perf_counter() - t) * 1000

        warmup = await run()
        sequential = [await run() for _ in range(20)]
        concurrent = await asyncio.gather(*[run() for _ in range(10)])
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "network_version": network["version"],
            "nodes": len(network["nodes"]),
            "pipes": len(network["pipes"]),
            "consumers": len(network["consumers"]),
            "transport": "HTTP loopback, FastAPI + two process workers + SQLite",
            "warmup_ms": round(warmup, 2),
            "sequential_runs": 20,
            "p95_ms": round(float(np.percentile(sequential, 95)), 2),
            "concurrent_clients": 10,
            "concurrent_p95_ms": round(float(np.percentile(concurrent, 95)), 2),
            "passed": bool(
                max(np.percentile(sequential, 95), np.percentile(concurrent, 95))
                <= 10000
            ),
            "sequential_ms": [round(x, 2) for x in sequential],
            "concurrent_ms": [round(x, 2) for x in concurrent],
        }
        with open("docs/kpi-http-report.json", "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

import hashlib
from datetime import datetime, timezone

PROFILES = {"normal", "pipe_break", "gradual_leak", "no_connection"}


def generate(network, previous, counter, profile="normal"):
    timestamp = datetime.now(timezone.utc).isoformat()
    nodes = {n.id: n for n in network.nodes}
    result = {}
    for sensor in network.sensors:
        old = previous.get(sensor.id)
        if old and old.get("mode") == "test_source":
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(old["timestamp"])
            ).total_seconds()
            result[sensor.id] = old | {
                "status": "no_connection" if age > 90 else "normal"
            }
            continue
        if profile == "no_connection" and old:
            result[sensor.id] = old | {"status": "no_connection"}
            continue
        seed = int(
            hashlib.sha256(f"{sensor.id}:{counter}".encode()).hexdigest()[:8], 16
        )
        supply = nodes[sensor.node_id].contour == "supply"
        unit = {"pressure": "бар", "temperature": "°C", "flow": "м³/ч"}[sensor.kind]
        base = {
            "pressure": 8 if supply else 3,
            "temperature": 90 if supply else 50,
            "flow": 20,
        }[sensor.kind]
        factor = (
            0.35
            if profile == "pipe_break"
            else max(0.2, 1 - counter * 0.025)
            if profile == "gradual_leak"
            else 1
        )
        value = round(
            base * (factor if sensor.kind == "pressure" else 1)
            + (seed % 100 - 50) / 1000,
            3,
        )
        result[sensor.id] = {
            "sensor_id": sensor.id,
            "value": value,
            "timestamp": timestamp,
            "unit": unit,
            "mode": "simulation",
            "profile": profile,
            "status": "no_connection"
            if profile == "no_connection"
            else "alarm"
            if profile in {"pipe_break", "gradual_leak"}
            else "normal",
        }
    return result

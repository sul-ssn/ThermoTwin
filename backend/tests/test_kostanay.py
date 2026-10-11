import json
import math
from pathlib import Path
import pytest
from app.kostanay import make_kostanay
from app.engine import supplied, simulate
from app.hydraulics import solve_hydraulics
from app.models import Constraints, SimulationInput

ROOT = Path(__file__).resolve().parents[2]
SX = 111320 * math.cos(math.radians(53.243136))


def distance(a, b):
    return math.hypot((a[0] - b[0]) * SX, (a[1] - b[1]) * 111320)


def distance_to_segment(p, a, b):
    dx, dy = (b[0] - a[0]) * SX, (b[1] - a[1]) * 111320
    px, py = (p[0] - a[0]) * SX, (p[1] - a[1]) * 111320
    t = max(0, min(1, (px * dx + py * dy) / (dx * dx + dy * dy))) if dx or dy else 0
    return math.hypot(px - t * dx, py - t * dy)


def test_roads_follow_the_committed_osm_geometry():
    raw = json.loads((ROOT / "data/geography/kostanay-yubileyny-osm.json").read_text())
    ways = {e["id"]: e for e in raw["elements"] if e["type"] == "way"}
    nodes = {
        e["id"]: (e["lon"], e["lat"]) for e in raw["elements"] if e["type"] == "node"
    }
    network = make_kostanay()
    for pipe in network.pipes:
        if pipe.route_kind != "road":
            continue
        way = ways[pipe.osm_way_id]
        assert "highway" in way["tags"]
        road = [nodes[n] for n in way["nodes"]]
        for p in pipe.geometry:
            assert (
                min(distance_to_segment(p, a, b) for a, b in zip(road, road[1:])) < 0.03
            )
        # Prevent replacing bends with a chord that cuts across blocks.
        for a, b in zip(pipe.geometry, pipe.geometry[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            assert (
                min(distance_to_segment(mid, u, v) for u, v in zip(road, road[1:]))
                < 0.03
            )
        assert pipe.length_m == pytest.approx(
            sum(distance(a, b) for a, b in zip(pipe.geometry, pipe.geometry[1:])),
            abs=0.03,
        )


def test_buildings_and_location_are_from_osm_not_a_grid():
    network = make_kostanay()
    assert network.geography.city == "Костанай"
    assert network.geography.region == "Костанайская область"
    assert network.geography.district == "Юбилейный"
    assert network.geography.boundary_osm_way_id == 657304160
    assert len(network.consumers) == 63
    assert any("Юбилейный, 22" in b.address for b in network.consumers)
    for b in network.consumers:
        assert b.osm_way_id and b.geometry and b.geometry[0] == b.geometry[-1]
        assert b.population is None
    assert all(
        63.59 < n.coordinates[0] < 63.63 and 53.23 < n.coordinates[1] < 53.26
        for n in network.nodes
    )
    supply = [p for p in network.pipes if p.contour == "supply"]
    returns = [p for p in network.pipes if p.contour == "return"]
    assert [p.geometry for p in supply] == [p.geometry for p in returns]
    assert any(len(p.geometry) > 2 for p in supply)


def test_district_is_served_and_reserve_routes_restore_supply():
    network = make_kostanay()
    states = {v.id: v.state for v in network.valves}
    assert len(supplied(network, states, Constraints())) == len(network.consumers)
    assert solve_hydraulics(network, states)["status"] == "success"
    before = network.model_dump()
    result = simulate(
        network,
        SimulationInput(
            network_version=network.version,
            incident={"type": "pipe_break", "segment_id": network.pipes[0].id},
        ),
    )
    assert len(result["variants"]) == 2
    assert result["variants"][0]["disconnected_buildings"] == 0
    assert result["variants"][1]["disconnected_buildings"] > 0
    assert result["variants"][0]["admissible"]
    assert network.model_dump() == before

import copy
import pytest
from app.models import Network, SimulationInput
from app.demo import make_demo
from app.engine import simulate, supplied
from app.hydraulics import solve_hydraulics


@pytest.fixture
def tiny():
    n = make_demo(2).model_dump()
    n["version"] = "test"
    n["consumers"] = [
        dict(
            id="B-test",
            name="Test",
            address="Test",
            supply_node="S-1",
            return_node="R-1",
            load_kw=46.52,
            population=5,
        )
    ]
    return Network.model_validate(n)


def req(n, segment="S-PIPE-0-1", event="pipe_break", backup=False):
    return SimulationInput(
        network_version=n.version,
        incident=dict(type=event, segment_id=segment),
        constraints=dict(allow_backup_routes=backup),
    )


def test_supply_break_disconnects(tiny):
    before = tiny.model_dump()
    r = simulate(tiny, req(tiny))
    assert r["affected_consumers"] == ["B-test"]
    assert r["valve_operations"] == [{"valve_id": "V-S-PIPE-0-1", "state": "closed"}]
    assert tiny.model_dump() == before


def test_return_break_disconnects(tiny):
    assert simulate(tiny, req(tiny, "R-PIPE-0-1"))["affected_consumers"] == ["B-test"]


def test_failed_valve_at_source_cannot_isolate(tiny):
    r = simulate(tiny, req(tiny, event="valve_failure"))
    assert r["status"] == "infeasible"


def test_reproducible(tiny):
    a = simulate(tiny, req(tiny))
    b = simulate(tiny, req(tiny))
    a.pop("execution_ms")
    b.pop("execution_ms")
    assert a == b


def test_unknown_endpoint_rejected(tiny):
    n = tiny.model_dump()
    n["pipes"][0]["end"] = "missing"
    with pytest.raises(ValueError):
        Network.model_validate(n)


def test_contour_mismatch_rejected(tiny):
    n = tiny.model_dump()
    n["pipes"][0]["end"] = "R-1"
    with pytest.raises(ValueError):
        Network.model_validate(n)


def test_unknown_valve_conservative(tiny):
    tiny.valves[0].state = "unknown"
    r = simulate(tiny, req(tiny))
    assert r["affected_consumers"] == ["B-test"]
    assert any("Неизвестная" in w for w in r["warnings"])


def test_hydraulic_analytic_linear(tiny):
    states = {v.id: v.state for v in tiny.valves}
    r = solve_hydraulics(tiny, states)
    assert r["status"] == "success"
    # 46.52 kW at 40 K -> exactly 1 m³/h. Δp = 0.0002 * 1 each contour.
    assert r["flows_m3h"]["S-PIPE-0-1"] == pytest.approx(1)
    assert r["pressures_bar"]["S-1"] == pytest.approx(7.9998)
    assert r["pressures_bar"]["R-1"] == pytest.approx(3.0002)
    assert r["minimum_differential_bar"] == pytest.approx(4.9996)


def test_low_pressure_reported(tiny):
    tiny.sources[0].supply_pressure_bar = 3.1
    assert (
        solve_hydraulics(tiny, {v.id: v.state for v in tiny.valves})["status"]
        == "outside_applicability"
    )


def test_pressure_event_keeps_connectivity(tiny):
    r = simulate(tiny, req(tiny, event="pressure_drop"))
    assert r["affected_consumers"] == []
    assert r["valve_operations"] == []


def test_backup_restores_consumers():
    n = make_demo(5)
    r = simulate(n, req(n, "S-PIPE-0-1", backup=True))
    assert len(r["variants"]) == 2
    assert (
        r["variants"][0]["disconnected_buildings"]
        < r["variants"][1]["disconnected_buildings"]
    )
    assert all(
        op["valve_id"] != "V-S-PIPE-0-1" or op["state"] == "closed"
        for op in r["valve_operations"]
    )


def test_control_network_size():
    n = make_demo()
    assert len(n.nodes) >= 1000 and len(n.pipes) >= 1500 and len(n.consumers) >= 300


def test_preclosed_damage_requires_no_operations(tiny):
    tiny.valves[0].state = "closed"
    r = simulate(tiny, req(tiny))
    assert r["valve_operations"] == []
    assert "S-PIPE-0-1" in r["affected_segments"]


def test_consumer_requires_common_source(tiny):
    from app.models import Source, Constraints

    # Supply connected only to source 1; return connected only to source 2.
    tiny.sources.append(
        Source(
            id="SECOND",
            supply_node="S-3",
            return_node="R-1",
            supply_pressure_bar=8,
            return_pressure_bar=3,
        )
    )
    states = {v.id: v.state for v in tiny.valves}
    states["V-R-PIPE-0-1"] = "closed"
    states["V-S-PIPE-2-3"] = "closed"
    assert supplied(tiny, states, Constraints()) == set()

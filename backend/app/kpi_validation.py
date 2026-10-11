"""Independent QA oracle: plain adjacency/BFS and dense nodal equations.

Deliberately does not import engine, hydraulics, or NetworkX graph helpers.
It checks correctness of the declared reduced linear model, not field accuracy.
"""

from collections import defaultdict
import math
import numpy as np


def reachability(network, states):
    adjacency = defaultdict(set)
    valves = {v.segment_id: v for v in network.valves}
    for p in network.pipes:
        valve = valves.get(p.id)
        if valve is None or states[valve.id] == "open":
            adjacency[p.start].add(p.end)
            adjacency[p.end].add(p.start)
    components = {}
    for source in network.sources:
        for contour in ("supply", "return"):
            origin = getattr(source, contour + "_node")
            seen, pending = {origin}, [origin]
            while pending:
                n = pending.pop()
                for other in adjacency[n] - seen:
                    seen.add(other)
                    pending.append(other)
            components[source.id, contour] = seen
    return components


def served(network, components, constraints):
    return {
        b.id
        for b in network.consumers
        if any(
            (
                not constraints.consider_supply
                or b.supply_node in components[s.id, "supply"]
            )
            and (
                not constraints.consider_return
                or b.return_node in components[s.id, "return"]
            )
            for s in network.sources
        )
    }


def dense_hydraulics(network, states, pressure_factor=1):
    components = reachability(network, states)
    # Physical demand always requires a complete pair of contours.
    both = type("Both", (), {"consider_supply": True, "consider_return": True})()
    connected = served(network, components, both)
    valves = {v.segment_id: v for v in network.valves}
    pressure, flow, residuals = {}, {}, []
    for contour in ("supply", "return"):
        active = set().union(*(components[s.id, contour] for s in network.sources))
        boundary = {
            getattr(s, contour + "_node"): getattr(s, contour + "_pressure_bar")
            * (pressure_factor if contour == "supply" else 1)
            for s in network.sources
        }
        unknown = sorted(active - boundary.keys())
        index = {n: i for i, n in enumerate(unknown)}
        demand = defaultdict(float)
        for b in network.consumers:
            if b.id in connected:
                demand[getattr(b, contour + "_node")] += (
                    b.load_kw / (1.163 * 40) * (1 if contour == "supply" else -1)
                )
        matrix = np.zeros((len(unknown), len(unknown)))
        rhs = np.array([-demand[n] for n in unknown], dtype=float)
        active_pipes = [
            p
            for p in network.pipes
            if p.contour == contour
            and p.start in active
            and (p.id not in valves or states[valves[p.id].id] == "open")
        ]
        for p in active_pipes:
            k = 1 / p.resistance
            for n, other in ((p.start, p.end), (p.end, p.start)):
                if n not in index:
                    continue
                i = index[n]
                matrix[i, i] += k
                if other in index:
                    matrix[i, index[other]] -= k
                else:
                    rhs[i] += k * boundary[other]
        values = np.linalg.solve(matrix, rhs) if unknown else np.array([])
        residuals.append(float(np.max(np.abs(matrix @ values - rhs))) if unknown else 0)
        pressure.update(boundary)
        pressure.update(dict(zip(unknown, map(float, values))))
        for p in active_pipes:
            flow[p.id] = (pressure[p.start] - pressure[p.end]) / p.resistance
    dp = [
        pressure[b.supply_node] - pressure[b.return_node]
        for b in network.consumers
        if b.id in connected
    ]
    minimum = min(dp) if dp else None
    pipes = {p.id: p for p in network.pipes}
    invalid = (
        (minimum is not None and minimum < 0.5)
        or any(v < 0 or v > 16 for v in pressure.values())
        or any(
            abs(q) / 3600 / (math.pi * (pipes[pid].diameter_mm / 1000) ** 2 / 4) > 3
            for pid, q in flow.items()
        )
    )
    return {
        "pressures": pressure,
        "flows": flow,
        "minimum": minimum,
        "status": "outside_applicability"
        if invalid
        else "insufficient_data"
        if minimum is None
        else "success",
        "residual": max(residuals),
    }


def check_hydraulics(network, states, actual, factor=1):
    expected = dense_hydraulics(network, states, factor)
    assert actual["status"] == expected["status"], (
        "Hydraulic status differs from independent solve"
    )
    assert set(actual["pressures_bar"]) == set(expected["pressures"])
    assert set(actual["flows_m3h"]) == set(expected["flows"])
    pressure_error = max(
        (abs(actual["pressures_bar"][n] - v) for n, v in expected["pressures"].items()),
        default=0,
    )
    # Production graph is undirected; its edge orientation is not pipe.start.
    # Compare flow magnitudes, and check signed balances on the independent solve.
    flow_error = max(
        (
            abs(abs(actual["flows_m3h"][p]) - abs(q))
            for p, q in expected["flows"].items()
        ),
        default=0,
    )
    assert pressure_error <= 0.000051, (
        "Pressure exceeds four-decimal rounding tolerance"
    )
    assert flow_error <= 0.000051, "Flow exceeds four-decimal rounding tolerance"
    assert expected["residual"] < 1e-7, "Nodal balance residual exceeds tolerance"
    if expected["minimum"] is None:
        assert actual["minimum_differential_bar"] is None
    else:
        assert abs(actual["minimum_differential_bar"] - expected["minimum"]) <= 0.000051
    return {
        "max_pressure_error_bar": pressure_error,
        "max_flow_magnitude_error_m3h": flow_error,
        "max_nodal_residual_m3h": expected["residual"],
    }


def check_result(network, request, result, numerical=True):
    initial = {v.id: v.state for v in network.valves}
    assert result["initial_valve_states"] == initial
    initial_components = reachability(network, initial)
    initially_served = served(network, initial_components, request.constraints)
    target = next(p for p in network.pipes if p.id == request.incident.segment_id)
    valves = {v.id: v for v in network.valves}
    direct = next((v for v in network.valves if v.segment_id == target.id), None)
    failed = direct.id if request.incident.type == "valve_failure" and direct else None
    if result["status"] == "infeasible":
        # If all operable sections were cut, an uncuttable path to either break
        # endpoint still remains. This independently proves impossibility.
        all_cut = {
            v.id: "closed"
            if v.operable and v.id != failed and v.state == "open"
            else v.state
            for v in network.valves
        }
        reachable = set().union(
            *(
                reachability(network, all_cut)[s.id, target.contour]
                for s in network.sources
            )
        )
        assert target.start in reachable or target.end in reachable
        assert result["variants"] == [] and result["valve_operations"] == []
        assert (
            set(result["affected_consumers"])
            == {b.id for b in network.consumers} - initially_served
        )
        return {"variants_checked": 0, "infeasible_proved": True}
    assert result["status"] == "completed" and result["variants"]
    stats = {
        "variants_checked": len(result["variants"]),
        "max_pressure_error_bar": 0.0,
        "max_flow_magnitude_error_m3h": 0.0,
        "max_nodal_residual_m3h": 0.0,
    }
    for variant in result["variants"]:
        states = initial.copy()
        acted = set()
        for op in variant["valve_operations"]:
            valve = valves[op["valve_id"]]
            assert valve.id not in acted and valve.id != failed
            assert valve.operable and valve.state != "unknown"
            assert op["state"] in {"open", "closed"}
            if op["state"] == "open":
                p = next(p for p in network.pipes if p.id == valve.segment_id)
                assert p.backup and request.constraints.allow_backup_routes
            states[valve.id] = op["state"]
            acted.add(valve.id)
        components = reachability(network, states)
        contour_reach = {
            c: set().union(*(components[s.id, c] for s in network.sources))
            for c in ("supply", "return")
        }
        connected = served(network, components, request.constraints)
        affected = {b.id for b in network.consumers} - connected
        assert len(variant["affected_consumers"]) == len(affected)
        assert set(variant["affected_consumers"]) == affected
        assert variant["disconnected_buildings"] == len(affected)
        assert set(variant["newly_affected_consumers"]) == initially_served - connected
        segments = {
            p.id
            for p in network.pipes
            if p.start not in contour_reach[p.contour]
            or p.end not in contour_reach[p.contour]
        }
        if request.incident.type != "pressure_drop":
            segments.add(target.id)
            assert (direct and states[direct.id] == "closed") or (
                target.start not in contour_reach[target.contour]
                and target.end not in contour_reach[target.contour]
            )
        else:
            assert states == initial and not variant["valve_operations"]
        assert set(variant["affected_segments"]) == segments
        assert variant["admissible"] == (
            variant["hydraulic_validation"]["status"] == "success"
        )
        population = [b.population for b in network.consumers if b.id in affected]
        assert variant["estimated_population"] == (
            sum(population) if all(p is not None for p in population) else None
        )
        if numerical:
            evidence = check_hydraulics(
                network,
                states,
                variant["hydraulic_validation"],
                request.incident.pressure_factor
                if request.incident.type == "pressure_drop"
                else 1,
            )
            for k, v in evidence.items():
                stats[k] = max(stats[k], v)
    best = result["variants"][0]
    for k in (
        "affected_consumers",
        "affected_segments",
        "disconnected_buildings",
        "valve_operations",
        "admissible",
        "hydraulic_validation",
    ):
        assert result[k] == best[k], (
            f"Selected result disagrees with first variant: {k}"
        )
    return stats

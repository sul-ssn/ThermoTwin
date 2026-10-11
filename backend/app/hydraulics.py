"""Steady linear resistance approximation: Δp = R Q.
R is supplied effective bar/(m³/h), not a Darcy friction factor.
Loads convert to volume using a fixed 40 K ΔT and 1.163 kWh/(m³ K).
This is an explicit reduced model, validated against linear analytic circuits.
"""

import math
import warnings
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve, MatrixRankWarning
import networkx as nx


def solve_hydraulics(network, states, pressure_factor=1):
    from .engine import graph, supplied
    from .models import Constraints

    served = supplied(network, states, Constraints())
    pressures = {}
    flows = {}
    disconnected = []
    try:
        for contour in ["supply", "return"]:
            g = graph(network, states, contour)
            boundary = {
                getattr(s, f"{contour}_node"): getattr(s, f"{contour}_pressure_bar")
                * (pressure_factor if contour == "supply" else 1)
                for s in network.sources
            }
            demand = {n: 0.0 for n in g.nodes}
            for b in network.consumers:
                if b.id not in served:
                    continue
                demand[getattr(b, f"{contour}_node")] += (
                    b.load_kw / (1.163 * 40) * (1 if contour == "supply" else -1)
                )
            active = set()
            for source in boundary:
                active.update(nx.node_connected_component(g, source))
            disconnected.extend(n for n in g if n not in active)
            unknown = [n for n in sorted(active) if n not in boundary]
            index = {n: i for i, n in enumerate(unknown)}
            matrix = lil_matrix((len(unknown), len(unknown)))
            rhs = np.array([-demand[n] for n in unknown])
            pipes = {p.id: p for p in network.pipes}
            for a, b, edge in g.edges(data=True):
                if a not in active:
                    continue
                conductance = sum(1 / pipes[pid].resistance for pid in edge["segments"])
                for n, other in [(a, b), (b, a)]:
                    if n not in index:
                        continue
                    i = index[n]
                    matrix[i, i] += conductance
                    if other in index:
                        matrix[i, index[other]] -= conductance
                    else:
                        rhs[i] += conductance * boundary[other]
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                values = spsolve(matrix.tocsr(), rhs) if unknown else []
            if not np.all(np.isfinite(values)):
                return {"status": "not_converged", "warnings": ["Нефинитное решение"]}
            pressures.update(boundary)
            pressures.update(dict(zip(unknown, map(float, values))))
            for a, b, edge in g.edges(data=True):
                if a in pressures and b in pressures:
                    for pid in edge["segments"]:
                        flows[pid] = (pressures[a] - pressures[b]) / pipes[
                            pid
                        ].resistance
        differential = [
            pressures[b.supply_node] - pressures[b.return_node]
            for b in network.consumers
            if b.id in served
            and b.supply_node in pressures
            and b.return_node in pressures
        ]
        min_dp = min(differential) if differential else None
        violations = []
        if min_dp is not None and min_dp < 0.5:
            violations.append("Перепад у потребителей ниже 0.5 бар")
        if any(p < 0 or p > 16 for p in pressures.values()):
            violations.append("Давление вне диапазона 0–16 бар")
        byid = {p.id: p for p in network.pipes}
        if any(
            abs(q) / 3600 / (math.pi * (byid[pid].diameter_mm / 1000) ** 2 / 4) > 3
            for pid, q in flows.items()
        ):
            violations.append("Скорость потока превышает 3 м/с")
        return {
            "status": "outside_applicability"
            if violations
            else ("insufficient_data" if min_dp is None else "success"),
            "model": "linear_effective_resistance",
            "minimum_differential_bar": round(min_dp, 4)
            if min_dp is not None
            else None,
            "pressures_bar": {k: round(v, 4) for k, v in pressures.items()},
            "flows_m3h": {k: round(v, 4) for k, v in flows.items()},
            "disconnected_nodes": disconnected,
            "warnings": violations,
            "assumptions": [
                "Δp=R·Q; R в бар/(м³/ч)",
                "Постоянная нагрузка; ΔT=40°C",
                "Без насосных кривых и тепловых потерь",
            ],
        }
    except (ValueError, RuntimeError, MatrixRankWarning) as e:
        return {"status": "not_converged", "warnings": [str(e)]}

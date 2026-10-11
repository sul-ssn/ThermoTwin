"""Undirected connectivity and valve-cut model. Hydraulic direction is solved separately."""

import time
import networkx as nx
from .models import Network, SimulationInput
from .hydraulics import solve_hydraulics


def graph(network, states, contour):
    g = nx.Graph()
    g.add_nodes_from(n.id for n in network.nodes if n.contour == contour)
    by_pipe = {v.segment_id: v for v in network.valves}
    for p in network.pipes:
        v = by_pipe.get(p.id)
        if p.contour == contour and (v is None or states[v.id] == "open"):
            if g.has_edge(p.start, p.end):
                g[p.start][p.end]["segments"].append(p.id)
            else:
                g.add_edge(p.start, p.end, segments=[p.id])
    return g


def reachable(network, states, contour):
    g = graph(network, states, contour)
    out = set()
    for s in network.sources:
        out.update(nx.node_connected_component(g, getattr(s, f"{contour}_node")))
    return out


def supplied(network, states, constraints):
    graphs = {c: graph(network, states, c) for c in ["supply", "return"]}
    out = set()
    for source in network.sources:
        reach = {
            c: nx.node_connected_component(graphs[c], getattr(source, f"{c}_node"))
            for c in ["supply", "return"]
        }
        out.update(
            b.id
            for b in network.consumers
            if (not constraints.consider_supply or b.supply_node in reach["supply"])
            and (not constraints.consider_return or b.return_node in reach["return"])
        )
    return out


def isolation_cut(network, states, target, failed):
    """Minimum valve cut separates both break endpoints from every source.
    Unvalved, failed, and unknown-state segments cannot be selected as actions.
    """
    g = nx.Graph()
    g.add_node("__source")
    g.add_node("__break")
    by_pipe = {v.segment_id: v for v in network.valves}
    for p in network.pipes:
        if p.contour != target.contour:
            continue
        v = by_pipe.get(p.id)
        if v and states[v.id] == "closed":
            continue
        capacity = (
            1
            if v and v.operable and v.id not in failed and states[v.id] == "open"
            else 1_000_000
        )
        if g.has_edge(p.start, p.end):
            g[p.start][p.end]["capacity"] += capacity
        else:
            g.add_edge(p.start, p.end, capacity=capacity)
    for s in network.sources:
        g.add_edge("__source", getattr(s, f"{target.contour}_node"), capacity=1_000_000)
    # Direct section isolation models a section valve; no real valve placement is inferred.
    direct = by_pipe.get(target.id)
    if direct and states[direct.id] == "closed":
        return []
    if (
        direct
        and direct.operable
        and direct.id not in failed
        and states[direct.id] == "open"
    ):
        return [direct.id]
    for endpoint in [target.start, target.end]:
        g.add_edge(endpoint, "__break", capacity=1_000_000)
    value, partition = nx.minimum_cut(g, "__source", "__break")
    if value >= 1_000_000:
        return None
    left, right = partition
    return [
        v.id
        for p in network.pipes
        if p.contour == target.contour
        and (
            (p.start in left and p.end in right) or (p.end in left and p.start in right)
        )
        for v in [by_pipe.get(p.id)]
        if v and states[v.id] == "open"
    ]


def simulate(network: Network, request: SimulationInput):
    started = time.perf_counter()
    target = next(
        (p for p in network.pipes if p.id == request.incident.segment_id), None
    )
    if not target:
        raise ValueError("UNKNOWN_SEGMENT")
    states = {v.id: v.state for v in network.valves}
    warnings = (
        [
            "Синтетическая модель. Рекомендации не предназначены для управления оборудованием."
        ]
        if network.demo
        else []
    )
    if any(s == "unknown" for s in states.values()):
        warnings.append(
            "Неизвестная арматура исключена из достижимости; оценка консервативная."
        )
    if (
        not request.constraints.consider_supply
        or not request.constraints.consider_return
    ):
        warnings.append(
            "Один из контуров исключён: результат не подтверждает полноценное теплоснабжение."
        )
    initial = supplied(network, states, request.constraints)
    failed = set()
    if request.incident.type == "valve_failure":
        v = next((v for v in network.valves if v.segment_id == target.id), None)
        if not v:
            raise ValueError("NO_VALVE_ON_SEGMENT")
        failed.add(v.id)
        warnings.append(
            "Отказ задвижки моделируется как невозможность её переключения; проверяется изоляция указанного участка."
        )
    operations = []
    if request.incident.type != "pressure_drop":
        cut = isolation_cut(network, states, target, failed)
        if cut is None:
            return dict(
                status="infeasible",
                affected_segments=[],
                affected_consumers=[
                    b.id for b in network.consumers if b.id not in initial
                ],
                disconnected_buildings=len(network.consumers) - len(initial),
                estimated_population=None,
                valve_operations=[],
                variants=[],
                hydraulic_validation={"status": "insufficient_data"},
                warnings=warnings
                + [
                    "Повреждение нельзя изолировать доступной арматурой. Зона отключения показывает только исходную недоступность, последствия повреждения не оценены."
                ],
                execution_ms=round((time.perf_counter() - started) * 1000, 2),
                initial_valve_states=states,
            )
        operations = [{"valve_id": vid, "state": "closed"} for vid in cut]
    else:
        warnings.append(
            "Снижение давления не разрывает топологию. Недостаточное теплоснабжение оценивается отдельно гидравликой."
        )

    def evaluate(ops, name):
        config = states.copy()
        for op in ops:
            config[op["valve_id"]] = op["state"]
        reached = supplied(network, config, request.constraints)
        affected = [b.id for b in network.consumers if b.id not in reached]
        factor = (
            request.incident.pressure_factor
            if request.incident.type == "pressure_drop"
            else 1
        )
        hydraulic = solve_hydraulics(network, config, factor)
        contour_reach = {c: reachable(network, config, c) for c in ["supply", "return"]}
        variant_segments = [
            p.id
            for p in network.pipes
            if p.start not in contour_reach[p.contour]
            or p.end not in contour_reach[p.contour]
        ]
        if (
            request.incident.type != "pressure_drop"
            and target.id not in variant_segments
        ):
            variant_segments.append(target.id)
        return dict(
            name=name,
            affected_segments=variant_segments,
            admissible=hydraulic["status"] == "success",
            affected_consumers=affected,
            newly_affected_consumers=sorted(initial - reached),
            valve_operations=ops,
            hydraulic_validation=hydraulic,
            disconnected_buildings=len(affected),
            estimated_population=sum(
                b.population for b in network.consumers if b.id in affected
            )
            if all(
                b.population is not None for b in network.consumers if b.id in affected
            )
            else None,
        )

    variants = [evaluate(operations, "Изоляция участка")]
    if request.constraints.allow_backup_routes and operations:
        config = states.copy()
        for op in operations:
            config[op["valve_id"]] = op["state"]
        # Greedy reserve restoration, always recheck that damaged section remains isolated.
        reserve_ops = operations.copy()
        pipes_by_id = {p.id: p for p in network.pipes}
        current_reach = {c: reachable(network, config, c) for c in ["supply", "return"]}
        current_supplied = supplied(network, config, request.constraints)
        for v in network.valves:
            pipe = pipes_by_id[v.segment_id]
            if (
                not pipe.backup
                or not v.operable
                or config[v.id] != "closed"
                or v.id in failed
            ):
                continue
            if (pipe.start in current_reach[pipe.contour]) == (
                pipe.end in current_reach[pipe.contour]
            ):
                continue
            trial = config | {v.id: "open"}
            reach = reachable(network, trial, target.contour)
            direct_closed = any(
                op["state"] == "closed"
                and next(x for x in network.valves if x.id == op["valve_id"]).segment_id
                == target.id
                for op in operations
            )
            if not direct_closed and (target.start in reach or target.end in reach):
                continue
            trial_supplied = supplied(network, trial, request.constraints)
            if len(trial_supplied) > len(current_supplied):
                reserve_ops.append({"valve_id": v.id, "state": "open"})
                config = trial
                current_supplied = trial_supplied
                current_reach = {
                    c: reachable(network, config, c) for c in ["supply", "return"]
                }
        if reserve_ops != operations:
            variants.append(evaluate(reserve_ops, "Изоляция с резервной веткой"))
    variants.sort(
        key=lambda x: (
            not x["admissible"],
            x["disconnected_buildings"],
            len(x["valve_operations"]),
        )
    )
    best = variants[0]
    if not best["admissible"]:
        warnings.append(
            "Нет варианта, подтверждённого гидравлическими ограничениями. Операции являются кандидатами, а не допустимыми рекомендациями."
        )
    final = states.copy()
    for op in best["valve_operations"]:
        final[op["valve_id"]] = op["state"]
    reached = {c: reachable(network, final, c) for c in ["supply", "return"]}
    segments = [
        p.id
        for p in network.pipes
        if p.start not in reached[p.contour] or p.end not in reached[p.contour]
    ]
    if request.incident.type != "pressure_drop" and target.id not in segments:
        segments.append(target.id)
    return dict(
        status="completed",
        **{k: v for k, v in best.items() if k not in {"name", "affected_segments"}},
        variants=variants,
        affected_segments=segments,
        warnings=warnings,
        initial_valve_states=states,
        execution_ms=round((time.perf_counter() - started) * 1000, 2),
    )

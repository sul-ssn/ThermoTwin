"""Build a model along OSM roads, with service connections to OSM buildings.

Run with PYTHONPATH=backend backend/.venv/bin/python scripts/build_kostanay.py.
Install scripts/requirements-geography.txt for regeneration; runtime is offline.
"""

import json
import math
from pathlib import Path
import networkx as nx
from shapely.geometry import LineString, Point, Polygon
from app.models import Network
from app.kostanay import VERSION

ROOT = Path(__file__).resolve().parents[1]
SX = 111320 * math.cos(math.radians(53.243136))
SY = 111320
ORIGIN = (63.613424, 53.243136)


def local(p):
    return ((p[0] - ORIGIN[0]) * SX, (p[1] - ORIGIN[1]) * SY)


def geographic(p):
    return (round(p[0] / SX + ORIGIN[0], 8), round(p[1] / SY + ORIGIN[1], 8))


def key(p):
    return (round(p[0], 4), round(p[1], 4))


def build():
    raw = json.loads((ROOT / "data/geography/kostanay-yubileyny-osm.json").read_text())
    elements = raw["elements"]
    coords = {e["id"]: (e["lon"], e["lat"]) for e in elements if e["type"] == "node"}
    boundary_way = next(e for e in elements if e["id"] == 657304160)
    boundary = [coords[n] for n in boundary_way["nodes"]]
    polygon = Polygon([local(p) for p in boundary])
    # The housing landuse ring is an OSM outline, not a cadastral boundary.
    # Include the perimeter road corridor, without spreading into nearby quarters.
    area = polygon.buffer(30)
    graph = nx.Graph()
    road_types = {
        "primary",
        "primary_link",
        "tertiary",
        "residential",
        "living_street",
        "unclassified",
        "service",
    }
    for way in elements:
        tags = way.get("tags", {})
        if way["type"] != "way" or tags.get("highway") not in road_types:
            continue
        if tags.get("service") == "parking_aisle" or tags.get("area") == "yes":
            continue
        points = [local(coords[n]) for n in way["nodes"]]
        for a, b in zip(points, points[1:]):
            clipped = LineString([a, b]).intersection(area)
            lines = (
                list(clipped.geoms)
                if clipped.geom_type == "MultiLineString"
                else [clipped]
            )
            for line in lines:
                if line.geom_type != "LineString" or line.length < 0.1:
                    continue
                u, v = key(line.coords[0]), key(line.coords[-1])
                if u != v:
                    graph.add_edge(
                        u,
                        v,
                        length=line.length,
                        osm=way["id"],
                        name=tags.get(
                            "name:ru", tags.get("name", "Внутриквартальный проезд")
                        ),
                    )
    component = max(nx.connected_components(graph), key=len)
    graph = graph.subgraph(component).copy()

    buildings = []
    for way in elements:
        tags = way.get("tags", {})
        if (
            way["type"] != "way"
            or "building" not in tags
            or len(way.get("nodes", [])) < 4
        ):
            continue
        ring = [coords[n] for n in way["nodes"]]
        shape = Polygon([local(p) for p in ring])
        if (
            not shape.is_valid
            or shape.area < 100
            or not polygon.covers(shape.representative_point())
        ):
            continue
        # Only heated residential / public / commercial buildings, not sheds.
        if tags["building"] in {
            "garage",
            "garages",
            "shed",
            "roof",
            "construction",
            "industrial",
            "warehouse",
        }:
            continue
        buildings.append(dict(osm=way["id"], tags=tags, ring=ring, shape=shape))

    source = min(
        graph, key=lambda p: Point(p).distance(Point(local((63.619, 53.2398))))
    )
    anchors = {source}
    connections = []
    for building in sorted(buildings, key=lambda b: b["osm"]):
        point = building["shape"].centroid
        candidates = []
        for a, b, attrs in graph.edges(data=True):
            line = LineString([a, b])
            projection = line.interpolate(line.project(point))
            distance = point.distance(projection)
            if distance > 150:
                continue
            connection = LineString([projection, point])
            # A service branch must not pass through another building.
            blocked = any(
                other["osm"] != building["osm"]
                and connection.intersects(other["shape"].buffer(-0.5))
                for other in buildings
            )
            if not blocked:
                candidates.append((distance, a, b, attrs, key(projection.coords[0])))
        if not candidates:
            raise ValueError(
                f"No unobstructed road connection for OSM building {building['osm']}"
            )
        _, a, b, attrs, attachment = min(candidates, key=lambda c: (c[0], c[1], c[2]))
        if Point(attachment).distance(Point(a)) < 0.2:
            attachment = a
        elif Point(attachment).distance(Point(b)) < 0.2:
            attachment = b
        else:
            graph.remove_edge(a, b)
            graph.add_edge(
                a, attachment, **{**attrs, "length": LineString([a, attachment]).length}
            )
            graph.add_edge(
                attachment, b, **{**attrs, "length": LineString([attachment, b]).length}
            )
        anchors.add(attachment)
        connections.append((building, attachment, key(point.coords[0])))

    # Remove unused dead-end roads; retain road loops as normally closed reserves.
    while True:
        leaves = [n for n in graph if graph.degree(n) <= 1 and n not in anchors]
        if not leaves:
            break
        graph.remove_nodes_from(leaves)
    # Merge degree-two shape vertices only within a single OSM way. Curves remain
    # in the polyline; junctions, building tees and provenance remain intact.
    for a, b, attrs in graph.edges(data=True):
        attrs["geometry"] = [a, b]
    changed = True
    while changed:
        changed = False
        for n in sorted(graph):
            if n in anchors or graph.degree(n) != 2:
                continue
            a, b = sorted(graph.neighbors(n))
            aa, bb = graph[a][n], graph[n][b]
            if graph.has_edge(a, b) or aa["osm"] != bb["osm"]:
                continue
            ga, gb = aa["geometry"], bb["geometry"]
            ga = ga if ga[0] == a else ga[::-1]
            gb = gb if gb[0] == n else gb[::-1]
            graph.remove_node(n)
            graph.add_edge(
                a,
                b,
                **{
                    **aa,
                    "length": aa["length"] + bb["length"],
                    "geometry": ga + gb[1:],
                },
            )
            changed = True
            break

    tree = nx.minimum_spanning_tree(graph, weight="length")
    rooted = nx.bfs_tree(tree, source)
    building_counts = {}
    for _, attachment, _ in connections:
        building_counts[attachment] = building_counts.get(attachment, 0) + 1
    for n in reversed(list(rooted)):
        building_counts[n] = building_counts.get(n, 0) + sum(
            building_counts[c] for c in rooted.successors(n)
        )
    node_indices = {
        p: i for i, p in enumerate([source] + sorted(set(graph) - {source}))
    }
    nodes, pipes, valves, consumers, sensors = [], [], [], [], []
    routes = []
    for a, b, attrs in sorted(graph.edges(data=True)):
        geometry = attrs["geometry"]
        if geometry[0] != a:
            geometry = geometry[::-1]
        routes.append(
            dict(
                a=node_indices[a],
                b=node_indices[b],
                length=attrs["length"],
                geometry=[geographic(p) for p in geometry],
                osm=attrs["osm"],
                name=attrs["name"],
                kind="road",
                backup=not tree.has_edge(a, b),
            )
        )
    # Put an operating trunk with an alternative road loop first for initial UI selection.
    bridges = {frozenset(e) for e in nx.bridges(graph)}
    index_points = {i: p for p, i in node_indices.items()}

    def route_priority(route):
        a, b = index_points[route["a"]], index_points[route["b"]]
        downstream = b if rooted.has_edge(a, b) else a
        return (
            route["backup"],
            frozenset((a, b)) in bridges,
            -building_counts[downstream],
            -route["length"],
        )

    routes.sort(key=route_priority)
    for building, attachment, center in connections:
        index = len(node_indices)
        node_indices[center] = index
        building["node"] = index
        routes.append(
            dict(
                a=node_indices[attachment],
                b=index,
                length=Point(attachment).distance(Point(center)),
                geometry=[geographic(attachment), geographic(center)],
                osm=building["osm"],
                name="Ввод в здание",
                kind="building_connection",
                backup=False,
            )
        )
    for contour, prefix in [("supply", "S"), ("return", "R")]:
        for point, i in node_indices.items():
            nodes.append(
                dict(
                    id=f"{prefix}-{i}",
                    type="source" if i == 0 else "junction",
                    coordinates=geographic(point),
                    contour=contour,
                )
            )
        for i, route in enumerate(routes):
            pid = f"{prefix}-{'ROAD' if route['kind'] == 'road' else 'CONN'}-{i:04d}"
            pipes.append(
                dict(
                    id=pid,
                    start=f"{prefix}-{route['a']}",
                    end=f"{prefix}-{route['b']}",
                    contour=contour,
                    length_m=round(route["length"], 2),
                    diameter_mm=250 if route["kind"] == "road" else 80,
                    resistance=max(
                        0.00001,
                        route["length"]
                        * (0.000004 if route["kind"] == "road" else 0.00002),
                    ),
                    geometry=route["geometry"],
                    backup=route["backup"],
                    route_kind=route["kind"],
                    osm_way_id=route["osm"],
                    name=route["name"],
                )
            )
            valves.append(
                dict(
                    id=f"V-{pid}",
                    segment_id=pid,
                    state="closed" if route["backup"] else "open",
                )
            )
        sensor_nodes = sorted({0, *[b["node"] for b, _, _ in connections][::5]})
        for i in sensor_nodes:
            sensors.append(
                dict(id=f"T-YUB-{prefix}-{i}", node_id=f"{prefix}-{i}", kind="pressure")
            )
    for building, _, _ in connections:
        tags, i = building["tags"], building["node"]
        number = tags.get("addr:housenumber")
        address = (
            f"Костанай, мкр. Юбилейный, {number}"
            if number
            else "Костанай, мкр. Юбилейный (номер не указан в OSM)"
        )
        name = tags.get(
            "name:ru",
            tags.get("name", f"Жилой дом {number}" if number else "Здание района"),
        )
        consumers.append(
            dict(
                id=f"B-OSM-{building['osm']}",
                name=name,
                address=address,
                supply_node=f"S-{i}",
                return_node=f"R-{i}",
                # Assumed loads only; no fabricated population or floor counts.
                load_kw=round(max(20, min(200, building["shape"].area * 0.10)), 2),
                population=None,
                geometry=building["ring"],
                osm_way_id=building["osm"],
            )
        )
    network = Network(
        version=VERSION,
        nodes=nodes,
        pipes=pipes,
        valves=valves,
        consumers=consumers,
        sensors=sensors,
        sources=[
            dict(
                id="HEAT-YUBILEYNY",
                supply_node="S-0",
                return_node="R-0",
                supply_pressure_bar=8,
                return_pressure_bar=3,
            )
        ],
        geography=dict(
            country="Казахстан",
            region="Костанайская область",
            city="Костанай",
            district="Юбилейный",
            center=ORIGIN,
            boundary=boundary,
            boundary_osm_way_id=boundary_way["id"],
            source="OpenStreetMap / Overpass API",
            retrieved_at=raw["osm3s"]["timestamp_osm_base"],
            attribution="© OpenStreetMap contributors · ODbL 1.0",
            model_note="Расчётная теплосеть вдоль дорог OSM; источник, арматура, диаметры и нагрузки смоделированы. Контур OSM — ориентир жилого района.",
        ),
    )
    target = ROOT / "backend/app/data/kostanay-yubileyny-network.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(network.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"{network.version}: {len(nodes)} nodes, {len(pipes)} pipes, {len(consumers)} buildings, {len(sensors)} sensors; {sum(r['backup'] for r in routes)} reserve routes"
    )
    return network


if __name__ == "__main__":
    build()

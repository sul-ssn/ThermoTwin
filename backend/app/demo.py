from .models import Network


def make_demo(size=25):
    nodes, pipes, valves, consumers, sensors = [], [], [], [], []

    def coord(i):
        return [71.395 + (i % size) * 0.00065, 51.155 + (i // size) * 0.00045]

    for contour, prefix in [("supply", "S"), ("return", "R")]:
        for i in range(size * size):
            nodes.append(
                dict(
                    id=f"{prefix}-{i}",
                    type="source" if i == 0 else "junction",
                    coordinates=coord(i),
                    contour=contour,
                )
            )
        for i in range(size * size):
            # Tree branches plus normally closed inter-row reserve connections.
            if i % size:
                pairs = [(i - 1, i, False)]
            elif i:
                pairs = [(i - size, i, False)]
            else:
                pairs = []
            if i >= size and i % size and i % 2 == 0:
                pairs.append((i - size, i, True))
            for a, b, backup in pairs:
                pid = f"{prefix}-PIPE-{a}-{b}"
                pipes.append(
                    dict(
                        id=pid,
                        start=f"{prefix}-{a}",
                        end=f"{prefix}-{b}",
                        contour=contour,
                        length_m=50,
                        diameter_mm=250 if a % size == 0 and b % size == 0 else 150,
                        resistance=0.0002,
                        geometry=[coord(a), coord(b)],
                        backup=backup,
                    )
                )
                # A valve bounds every section in this synthetic test topology.
                valves.append(
                    dict(
                        id=f"V-{pid}",
                        segment_id=pid,
                        state="closed" if backup else "open",
                    )
                )
        for i in range(0, size * size, 50):
            sensors.append(
                dict(id=f"T-{prefix}-{i}", node_id=f"{prefix}-{i}", kind="pressure")
            )
    for i in range(1, size * size, 2):
        consumers.append(
            dict(
                id=f"B-{i}",
                name=f"Жилой дом {i}",
                address=f"мкр. Юбилейный, {i}",
                supply_node=f"S-{i}",
                return_node=f"R-{i}",
                load_kw=20 + (i % 10) * 2,
                population=30 + i % 90,
            )
        )
    return Network(
        version="demo-2",
        nodes=nodes,
        pipes=pipes,
        valves=valves,
        consumers=consumers,
        sensors=sensors,
        sources=[
            dict(
                id="HEAT-1",
                supply_node="S-0",
                return_node="R-0",
                supply_pressure_bar=8,
                return_pressure_bar=3,
            )
        ],
    )

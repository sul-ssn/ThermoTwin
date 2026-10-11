from typing import Literal
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field, model_validator


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")


class Node(BaseModel):
    id: str
    type: Literal["junction", "source", "consumer"] = "junction"
    coordinates: tuple[float, float]

    @model_validator(mode="after")
    def validate_coordinates(self):
        if not (
            -180 <= self.coordinates[0] <= 180 and -90 <= self.coordinates[1] <= 90
        ):
            raise ValueError("Coordinates outside WGS84 bounds")
        return self

    contour: Literal["supply", "return"]


class Pipe(BaseModel):
    id: str
    start: str
    end: str
    contour: Literal["supply", "return"]
    length_m: float = Field(gt=0)
    diameter_mm: float = Field(gt=0)
    resistance: float = Field(gt=0)
    geometry: list[tuple[float, float]] = Field(min_length=2)
    backup: bool = False
    route_kind: Literal["road", "building_connection"] | None = None
    osm_way_id: int | None = None
    name: str | None = None


class Valve(BaseModel):
    id: str
    segment_id: str
    state: Literal["open", "closed", "unknown"] = "open"
    operable: bool = True


class Consumer(BaseModel):
    id: str
    name: str
    address: str
    supply_node: str
    return_node: str
    load_kw: float = Field(gt=0)
    population: int | None = Field(default=None, ge=0)
    geometry: list[tuple[float, float]] | None = None
    osm_way_id: int | None = None

    @model_validator(mode="after")
    def validate_geometry(self):
        if self.geometry is not None and (
            len(self.geometry) < 4
            or self.geometry[0] != self.geometry[-1]
            or any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in self.geometry)
        ):
            raise ValueError("Consumer footprint must be a closed WGS84 ring")
        return self


class Geography(BaseModel):
    country: str
    region: str
    city: str
    district: str
    center: tuple[float, float]
    boundary: list[tuple[float, float]]
    boundary_osm_way_id: int
    source: str
    retrieved_at: str
    attribution: str
    model_note: str

    @model_validator(mode="after")
    def validate_geometry(self):
        if (
            len(self.boundary) < 4
            or self.boundary[0] != self.boundary[-1]
            or any(
                not (-180 <= x <= 180 and -90 <= y <= 90)
                for x, y in [self.center, *self.boundary]
            )
        ):
            raise ValueError(
                "District geometry must be a closed WGS84 ring with a valid center"
            )
        return self


class Source(BaseModel):
    id: str
    supply_node: str
    return_node: str
    supply_pressure_bar: float
    return_pressure_bar: float


class Sensor(BaseModel):
    id: str
    node_id: str
    kind: Literal["pressure", "temperature", "flow"]


class Network(BaseModel):
    version: str = Field(min_length=1)
    demo: bool = True
    nodes: list[Node]
    pipes: list[Pipe]
    valves: list[Valve]
    consumers: list[Consumer]
    sources: list[Source]
    sensors: list[Sensor] = []
    geography: Geography | None = None

    @model_validator(mode="after")
    def validate_links(self):
        collections = [
            self.nodes,
            self.pipes,
            self.valves,
            self.consumers,
            self.sources,
            self.sensors,
        ]
        ids = [item.id for group in collections for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError("Object IDs must be globally unique")
        nodes = {n.id: n for n in self.nodes}
        pipes = {p.id: p for p in self.pipes}
        for p in self.pipes:
            if p.start not in nodes or p.end not in nodes:
                raise ValueError(f"{p.id}: unknown endpoint")
            if nodes[p.start].contour != p.contour or nodes[p.end].contour != p.contour:
                raise ValueError(f"{p.id}: contour mismatch")
            if p.start == p.end:
                raise ValueError(f"{p.id}: self-loop")
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in p.geometry):
                raise ValueError(f"{p.id}: invalid WGS84 geometry")
            if (
                tuple(p.geometry[0]) != nodes[p.start].coordinates
                or tuple(p.geometry[-1]) != nodes[p.end].coordinates
            ):
                raise ValueError(f"{p.id}: geometry endpoints mismatch")
        if not self.sources:
            raise ValueError("At least one heat source is required")
        for obj in [*self.consumers, *self.sources]:
            for field, contour in [
                ("supply_node", "supply"),
                ("return_node", "return"),
            ]:
                key = getattr(obj, field)
                if key not in nodes or nodes[key].contour != contour:
                    raise ValueError(f"{obj.id}: invalid {field}")
        valve_segments = [v.segment_id for v in self.valves]
        if len(set(valve_segments)) != len(valve_segments):
            raise ValueError("This MVP supports one isolation valve per segment")
        for v in self.valves:
            if v.segment_id not in pipes:
                raise ValueError(f"{v.id}: unknown segment")
        for s in self.sensors:
            if s.node_id not in nodes:
                raise ValueError(f"{s.id}: unknown sensor node")
        return self


class IncidentInput(BaseModel):
    type: Literal["pipe_break", "valve_failure", "pressure_drop"]
    segment_id: str
    pressure_factor: float = Field(default=0.6, gt=0, le=1)


class Constraints(BaseModel):
    consider_supply: bool = True
    consider_return: bool = True
    allow_backup_routes: bool = True


class SimulationInput(BaseModel):
    network_version: str
    incident: IncidentInput
    constraints: Constraints = Field(default_factory=Constraints)


class Reading(BaseModel):
    sensor_id: str
    value: float
    timestamp: str

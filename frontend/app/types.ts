export type Network = {
  version: string;
  demo: boolean;
  geography?: {
    country: string;
    region: string;
    city: string;
    district: string;
    center: [number, number];
    boundary: [number, number][];
    model_note: string;
    attribution: string;
  } | null;
  nodes: {
    id: string;
    type: string;
    coordinates: [number, number];
    contour: string;
  }[];
  pipes: {
    id: string;
    start: string;
    end: string;
    contour: string;
    length_m: number;
    diameter_mm: number;
    resistance: number;
    geometry: [number, number][];
    backup: boolean;
    route_kind?: "road" | "building_connection" | null;
    osm_way_id?: number | null;
    name?: string | null;
  }[];
  valves: {
    id: string;
    segment_id: string;
    state: string;
    operable: boolean;
  }[];
  consumers: {
    id: string;
    name: string;
    address: string;
    supply_node: string;
    return_node: string;
    population: number | null;
    load_kw: number;
    geometry?: [number, number][] | null;
  }[];
  sources: { id: string; supply_node: string; return_node: string }[];
  sensors: { id: string; node_id: string; kind: string }[];
};
export type Hydraulic = {
  status: string;
  minimum_differential_bar?: number;
  warnings?: string[];
  assumptions?: string[];
};
export type Variant = {
  affected_segments?: string[];
  name: string;
  admissible: boolean;
  affected_consumers: string[];
  newly_affected_consumers: string[];
  disconnected_buildings: number;
  estimated_population: number | null;
  valve_operations: { valve_id: string; state: string }[];
  hydraulic_validation: Hydraulic;
};
export type Simulation = Variant & {
  simulation_id: string;
  network_version: string;
  status: string;
  affected_segments: string[];
  variants: Variant[];
  warnings: string[];
  execution_ms: number;
  created_at: string;
  request: { incident: { type: string; segment_id: string } };
};
export type Reading = {
  sensor_id: string;
  value: number;
  timestamp: string;
  status: string;
  unit?: string;
  mode: string;
};

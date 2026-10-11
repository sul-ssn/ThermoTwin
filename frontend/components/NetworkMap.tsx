"use client";
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Network, Simulation, Reading } from "../app/types";

function midpoint(points: [number, number][]): [number, number] {
  const scale = Math.cos((points[0][1] * Math.PI) / 180);
  const lengths = points
    .slice(1)
    .map((p, i) =>
      Math.hypot((p[0] - points[i][0]) * scale, p[1] - points[i][1]),
    );
  let remaining = lengths.reduce((a, b) => a + b, 0) / 2;
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i]) {
      const t = lengths[i] ? remaining / lengths[i] : 0;
      return [
        points[i][0] + t * (points[i + 1][0] - points[i][0]),
        points[i][1] + t * (points[i + 1][1] - points[i][1]),
      ];
    }
    remaining -= lengths[i];
  }
  return points[0];
}
export default function NetworkMap({
  network,
  result,
  selected,
  onSelect,
  showReturn,
  showConsumers,
  showSensors,
  readings,
  showSupply = true,
  showValves = true,
  showBasemap = true,
  showZones = true,
}: {
  network: Network;
  result: Simulation | null;
  selected: string;
  onSelect: (id: string) => void;
  showReturn: boolean;
  showConsumers: boolean;
  showSensors: boolean;
  readings: Reading[];
  showSupply?: boolean;
  showValves?: boolean;
  showBasemap?: boolean;
  showZones?: boolean;
}) {
  const [mapError, setMapError] = useState("");
  const ref = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null),
    callback = useRef(onSelect);
  callback.current = onSelect;
  useEffect(() => {
    if (!ref.current) return;
    maplibregl.setWorkerUrl(
      new URL(
        "maplibre-gl/dist/maplibre-gl-worker.mjs",
        import.meta.url,
      ).toString(),
    );
    const m = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution:
              '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxzoom: 19,
          },
        },
        layers: [
          {
            id: "bg",
            type: "background",
            paint: { "background-color": "#edf2f5" },
          },
          {
            id: "basemap",
            type: "raster",
            source: "basemap",
            paint: { "raster-opacity": 0.75, "raster-saturation": -0.4 },
          },
        ],
      },
      center: network.geography?.center ??
        network.nodes[0]?.coordinates ?? [63.613424, 53.243136],
      zoom: 14.5,
      attributionControl: { compact: true },
    });
    m.on("error", (e) => {
      if ("sourceId" in e && e.sourceId === "basemap") {
        setMapError("Подложка недоступна. Схема сети продолжает работать.");
        m.setLayoutProperty("basemap", "visibility", "none");
      } else setMapError(e.error.message);
    });
    m.on("idle", () => {
      ref.current?.setAttribute("data-ready", "true");
      const rendered = m.getLayer("pipes")
        ? m.queryRenderedFeatures({ layers: ["pipes", "buildings"] }).length
        : 0;
      ref.current?.setAttribute("data-rendered", String(rendered));
    });
    m.addControl(new maplibregl.NavigationControl(), "top-left");
    map.current = m;
    m.on("style.load", () => {
      m.addSource("network", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "district-boundary",
        type: "line",
        source: "network",
        filter: ["==", ["get", "kind"], "district"],
        paint: {
          "line-color": "#7287a0",
          "line-width": 1.5,
          "line-dasharray": [4, 3],
          "line-opacity": 0.6,
        },
      });
      m.addLayer({
        id: "building-footprints",
        type: "fill",
        source: "network",
        filter: ["==", ["get", "kind"], "footprint"],
        paint: {
          "fill-color": [
            "case",
            ["get", "affected"],
            "#ff4d4f",
            ["get", "selected"],
            "#246bfd",
            "#8093ab",
          ],
          "fill-opacity": 0.22,
        },
      });
      m.addLayer({
        id: "building-outlines",
        type: "line",
        source: "network",
        filter: ["==", ["get", "kind"], "footprint"],
        paint: {
          "line-color": [
            "case",
            ["get", "affected"],
            "#ff4d4f",
            ["get", "selected"],
            "#246bfd",
            "#8093ab",
          ],
          "line-width": 1,
        },
      });
      m.addLayer({
        id: "zones",
        type: "fill",
        source: "network",
        filter: ["==", ["get", "kind"], "zone"],
        paint: { "fill-color": "#ff4d4f", "fill-opacity": 0.12 },
      });
      m.addLayer({
        id: "zone-border",
        type: "line",
        source: "network",
        filter: ["==", ["get", "kind"], "zone"],
        paint: {
          "line-color": "#ff6264",
          "line-width": 1.3,
          "line-dasharray": [3, 2],
        },
      });
      m.addLayer({
        id: "pipes",
        type: "line",
        source: "network",
        filter: ["==", ["get", "kind"], "pipe"],
        paint: {
          "line-color": [
            "case",
            ["get", "affected"],
            "#ff4d4f",
            ["get", "selected"],
            "#17202a",
            ["==", ["get", "contour"], "return"],
            "#2875ff",
            ["get", "backup"],
            "#63cecc",
            "#ff922d",
          ],
          "line-width": [
            "case",
            ["get", "selected"],
            5,
            ["get", "affected"],
            3.5,
            1.5,
          ],
          "line-opacity": ["case", ["get", "backup"], 0.35, 0.85],
          "line-offset": ["case", ["==", ["get", "contour"], "return"], 2, -2],
        },
      });
      m.addLayer({
        id: "buildings",
        type: "circle",
        source: "network",
        filter: ["==", ["get", "kind"], "consumer"],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13,
            1.5,
            16,
            3,
            18,
            5,
          ],
          "circle-color": ["case", ["get", "affected"], "#ff4d4f", "#8393a6"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      });
      m.addLayer({
        id: "valves",
        type: "circle",
        source: "network",
        filter: ["==", ["get", "kind"], "valve"],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13,
            1.5,
            16,
            2.5,
            18,
            4,
          ],
          "circle-color": ["case", ["get", "affected"], "#ff9128", "#ffffff"],
          "circle-stroke-color": "#4385ee",
          "circle-stroke-width": 1,
        },
      });
      m.addLayer({
        id: "sensors",
        type: "circle",
        source: "network",
        filter: ["==", ["get", "kind"], "sensor"],
        paint: {
          "circle-radius": 5,
          "circle-color": [
            "case",
            ["==", ["get", "status"], "no_connection"],
            "#6e7887",
            ["==", ["get", "status"], "alarm"],
            "#ff4d4f",
            "#18b78a",
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      m.addLayer({
        id: "sources",
        type: "circle",
        source: "network",
        filter: ["==", ["get", "kind"], "source"],
        paint: {
          "circle-radius": 9,
          "circle-color": "#ff9128",
          "circle-stroke-color": "#fff2d4",
          "circle-stroke-width": 2,
        },
      });
      for (const layer of [
        "pipes",
        "buildings",
        "valves",
        "sensors",
        "sources",
        "building-footprints",
      ]) {
        m.on("click", layer, (e) => {
          const f = e.features?.[0];
          if (f) callback.current(String(f.properties?.id));
        });
        m.on(
          "mouseenter",
          layer,
          () => (m.getCanvas().style.cursor = "pointer"),
        );
        m.on("mouseleave", layer, () => (m.getCanvas().style.cursor = ""));
      }
    });
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const update = () => {
      const nodes = Object.fromEntries(network.nodes.map((n) => [n.id, n]));
      const affected = new Set(result?.affected_segments ?? []),
        buildings = new Set(result?.affected_consumers ?? []);
      const operations = new Set(
        result?.valve_operations.map((o) => o.valve_id) ?? [],
      );
      const features: any[] = network.pipes
        .filter((p) => (p.contour === "supply" ? showSupply : showReturn))
        .map((p) => ({
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: p.geometry,
          },
          properties: {
            id: p.id,
            kind: "pipe",
            contour: p.contour,
            backup: p.backup,
            affected: affected.has(p.id),
            selected: p.id === selected,
          },
        }));
      if (showConsumers)
        for (const b of network.consumers) {
          if (b.geometry)
            features.push({
              type: "Feature",
              geometry: { type: "Polygon", coordinates: [b.geometry] },
              properties: {
                id: b.id,
                kind: "footprint",
                affected: buildings.has(b.id),
                selected: selected === b.id,
              },
            });
          features.push({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: nodes[b.supply_node].coordinates,
            },
            properties: {
              id: b.id,
              kind: "consumer",
              affected: buildings.has(b.id),
            },
          });
        }
      if (network.geography)
        features.unshift({
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [network.geography.boundary],
          },
          properties: { kind: "district", id: "yubileyny-boundary" },
        });
      if (showValves)
        for (const v of network.valves) {
          const p = network.pipes.find((p) => p.id === v.segment_id);
          if (p && (p.contour === "supply" ? showSupply : showReturn))
            features.push({
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: midpoint(p.geometry),
              },
              properties: {
                id: v.id,
                kind: "valve",
                affected: operations.has(v.id),
              },
            });
        }
      if (showSensors)
        for (const s of network.sensors)
          features.push({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: nodes[s.node_id].coordinates,
            },
            properties: {
              id: s.id,
              kind: "sensor",
              status:
                readings.find((r) => r.sensor_id === s.id)?.status ??
                "no_connection",
            },
          });
      for (const s of network.sources)
        features.push({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: nodes[s.supply_node].coordinates,
          },
          properties: { id: s.id, kind: "source" },
        });
      if (showZones && buildings.size) {
        const footprints = network.consumers.filter(
          (b) => buildings.has(b.id) && b.geometry,
        );
        if (footprints.length) {
          features.unshift({
            type: "Feature",
            geometry: {
              type: "MultiPolygon",
              coordinates: footprints.map((b) => [b.geometry!]),
            },
            properties: { kind: "zone", id: "affected-buildings" },
          });
        } else {
          const pts = network.consumers
            .filter((b) => buildings.has(b.id))
            .map((b) => nodes[b.supply_node].coordinates);
          if (pts.length) {
            const pad = 0.00008,
              x0 = Math.min(...pts.map((p) => p[0])) - pad,
              x1 = Math.max(...pts.map((p) => p[0])) + pad,
              y0 = Math.min(...pts.map((p) => p[1])) - pad,
              y1 = Math.max(...pts.map((p) => p[1])) + pad;
            features.unshift({
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [x0, y0],
                    [x1, y0],
                    [x1, y1],
                    [x0, y1],
                    [x0, y0],
                  ],
                ],
              },
              properties: { kind: "zone", id: "affected-envelope" },
            });
          }
        }
      }
      ref.current?.setAttribute("data-ready", "false");
      ref.current?.setAttribute("data-features", String(features.length));
      (m.getSource("network") as maplibregl.GeoJSONSource)?.setData({
        type: "FeatureCollection",
        features,
      });
    };
    if (m.getSource("network")) update();
    else m.once("style.load", update);
    return () => {
      m.off("style.load", update);
    };
  }, [
    network,
    result,
    selected,
    showReturn,
    showConsumers,
    showSensors,
    readings,
    showSupply,
    showValves,
    showZones,
  ]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const fit = () => {
      if (!network.nodes.length) return;
      const points =
        network.geography?.boundary ?? network.nodes.map((n) => n.coordinates);
      const bounds = points.reduce(
        (b, p) => b.extend(p),
        new maplibregl.LngLatBounds(points[0], points[0]),
      );
      m.fitBounds(bounds, {
        padding: {
          top: 70,
          bottom: 75,
          left: m.getContainer().clientWidth > 600 ? 230 : 45,
          right: 50,
        },
        maxZoom: 16,
        duration: 0,
      });
    };
    if (m.getSource("network")) fit();
    else m.once("style.load", fit);
    return () => {
      m.off("style.load", fit);
    };
  }, [network.version]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const visibility = () => {
      if (m.getLayer("basemap"))
        m.setLayoutProperty(
          "basemap",
          "visibility",
          showBasemap ? "visible" : "none",
        );
    };
    if (m.isStyleLoaded()) visibility();
    else m.once("style.load", visibility);
    return () => {
      m.off("style.load", visibility);
    };
  }, [showBasemap]);
  return (
    <>
      <div className="map-canvas" ref={ref} />
      {mapError && <div className="map-error">Ошибка карты: {mapError}</div>}
    </>
  );
}

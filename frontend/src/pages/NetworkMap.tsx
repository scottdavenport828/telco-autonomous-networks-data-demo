import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type FilterSpecification, type Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import clsx from "clsx";
import { api, type MapCell, type MapCellsResponse, type MapEvent } from "../api/client";

const MAP_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm-tiles", type: "raster" as const, source: "osm" }],
};

const NYC_CENTER: [number, number] = [-73.9857, 40.7484];

type Layers = {
  cells: boolean;
  sectors: boolean;
  heatmap: boolean;
  anomalies: boolean;
  agentActivity: boolean;
};

type WindowKey = "5m" | "15m" | "1h" | "24h" | "live";
const WINDOW_OPTIONS: WindowKey[] = ["5m", "15m", "1h", "24h", "live"];
const WINDOW_TO_QUERY: Record<WindowKey, string> = {
  "5m": "5m",
  "15m": "15m",
  "1h": "1h",
  "24h": "24h",
  live: "5m",
};

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

function sectorPolygon(lat: number, lon: number, azimuth: number, rangeM: number, halfAngleDeg = 30) {
  const earthR = 6_371_000;
  const startAngle = azimuth - halfAngleDeg;
  const endAngle = azimuth + halfAngleDeg;
  const steps = 12;
  const coords: [number, number][] = [[lon, lat]];
  for (let i = 0; i <= steps; i++) {
    const a = ((startAngle + ((endAngle - startAngle) * i) / steps) * Math.PI) / 180;
    const dLat = (rangeM / earthR) * Math.cos(a) * (180 / Math.PI);
    const dLon =
      ((rangeM / earthR) * Math.sin(a) * (180 / Math.PI)) /
      Math.cos((lat * Math.PI) / 180);
    coords.push([lon + dLon, lat + dLat]);
  }
  coords.push([lon, lat]);
  return coords;
}

function cellsToFeatureCollection(cells: MapCell[], thresholds: { erab_success_rate_min: number; retainability_max: number }) {
  const features = cells.map((c) => {
    const violating =
      (c.erab_success_rate !== null && c.erab_success_rate < thresholds.erab_success_rate_min) ||
      (c.retainability !== null && c.retainability > thresholds.retainability_max);
    const fill = !c.is_active
      ? "#94a3b8" // slate-400 — context cells
      : c.erab_success_rate === null
        ? "#cbd5e1" // slate-300 — active but no data yet
        : violating
          ? "#dc2626" // red-600
          : c.erab_success_rate < 99
            ? "#f59e0b" // amber-500
            : "#10b981"; // emerald-500
    return {
      type: "Feature" as const,
      geometry: {
        type: "Polygon" as const,
        coordinates: [sectorPolygon(c.lat, c.lon, c.azimuth, c.range_m)],
      },
      properties: {
        ...c,
        fill,
        violating: violating ? 1 : 0,
      },
    };
  });
  return { type: "FeatureCollection" as const, features };
}

function siteCentroidsFc(cells: MapCell[]) {
  const grouped = new Map<string, { lat: number; lon: number; site_name: string; n_active: number; n_violating: number }>();
  for (const c of cells) {
    const key = c.enodeb_id;
    const existing = grouped.get(key);
    if (existing) {
      if (c.is_active) existing.n_active += 1;
    } else {
      grouped.set(key, {
        lat: c.lat,
        lon: c.lon,
        site_name: c.site_name,
        n_active: c.is_active ? 1 : 0,
        n_violating: 0,
      });
    }
  }
  return {
    type: "FeatureCollection" as const,
    features: [...grouped.entries()].map(([enodeb_id, v]) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [v.lon, v.lat] },
      properties: { enodeb_id, ...v, is_active: v.n_active > 0 ? 1 : 0 },
    })),
  };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NetworkMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [cells, setCells] = useState<MapCell[]>([]);
  const [thresholds, setThresholds] = useState<MapCellsResponse["thresholds"]>({
    erab_success_rate_min: 97,
    retainability_max: 3,
  });
  const [layers, setLayers] = useState<Layers>({
    cells: true,
    sectors: true,
    heatmap: false,
    anomalies: true,
    agentActivity: true,
  });
  const [windowKey, setWindowKey] = useState<WindowKey>("15m");
  const [capPerSec, setCapPerSec] = useState(4);
  const [recentEvents, setRecentEvents] = useState<MapEvent[]>([]);
  const eventQueueRef = useRef<MapEvent[]>([]);
  const lastDrawAtRef = useRef<number>(0);

  // Fetch cells once on mount.
  useEffect(() => {
    api
      .mapCells()
      .then((r) => {
        setCells(r.rows);
        setThresholds(r.thresholds);
      })
      .catch((e) => console.error("mapCells failed", e));
  }, []);

  // Init the map once the container is available.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: NYC_CENTER,
      zoom: 12.6,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = m;
    return () => {
      m.remove();
      mapRef.current = null;
    };
  }, []);

  // Push cell + sector layers to the map whenever cells change.
  useEffect(() => {
    const m = mapRef.current;
    if (!m || cells.length === 0) return;
    const apply = () => {
      const sectorsFc = cellsToFeatureCollection(cells, thresholds);
      const sitesFc = siteCentroidsFc(cells);
      if (m.getSource("sectors")) {
        (m.getSource("sectors") as maplibregl.GeoJSONSource).setData(sectorsFc);
      } else {
        m.addSource("sectors", { type: "geojson", data: sectorsFc });
      }
      if (m.getSource("sites")) {
        (m.getSource("sites") as maplibregl.GeoJSONSource).setData(sitesFc);
      } else {
        m.addSource("sites", { type: "geojson", data: sitesFc });
      }
      if (!m.getLayer("sectors-fill")) {
        m.addLayer({
          id: "sectors-fill",
          type: "fill",
          source: "sectors",
          paint: { "fill-color": ["get", "fill"], "fill-opacity": 0.32 },
        });
        m.addLayer({
          id: "sectors-line",
          type: "line",
          source: "sectors",
          paint: { "line-color": ["get", "fill"], "line-opacity": 0.8, "line-width": 1 },
        });
      }
      if (!m.getLayer("cells-dot")) {
        m.addLayer({
          id: "cells-dot",
          type: "circle",
          source: "sites",
          paint: {
            "circle-radius": ["case", ["==", ["get", "is_active"], 1], 6, 3],
            "circle-color": ["case", ["==", ["get", "is_active"], 1], "#0f172a", "#94a3b8"],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1,
          },
        });
        m.addLayer({
          id: "cells-label",
          type: "symbol",
          source: "sites",
          layout: {
            "text-field": ["get", "site_name"],
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-allow-overlap": false,
          },
          paint: { "text-color": "#0f172a", "text-halo-color": "#ffffff", "text-halo-width": 1.2 },
        });
      }
      if (!m.getLayer("event-pulse")) {
        m.addSource("events", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({
          id: "event-pulse",
          type: "circle",
          source: "events",
          paint: {
            // Pulse expands from 8 to 48px over the lifetime; opacity fades.
            "circle-radius": ["interpolate", ["linear"], ["get", "age"], 0, 8, 1, 48],
            "circle-color": [
              "match",
              ["get", "kind"],
              "anomaly", "#dc2626",
              "agent_call", "#0ea5e9",
              "incident", "#f59e0b",
              "#7c3aed",
            ],
            "circle-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 0.85, 1, 0],
            "circle-stroke-color": [
              "match",
              ["get", "kind"],
              "anomaly", "#7f1d1d",
              "agent_call", "#0c4a6e",
              "incident", "#92400e",
              "#4c1d95",
            ],
            "circle-stroke-width": 2,
            "circle-stroke-opacity": ["interpolate", ["linear"], ["get", "age"], 0, 0.9, 1, 0],
          },
        });
      }
    };
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [cells, thresholds]);

  // Apply layer-toggle state.
  useEffect(() => {
    const m = mapRef.current;
    if (!m) return;
    const setVis = (id: string, v: boolean) => {
      if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", v ? "visible" : "none");
    };
    setVis("sectors-fill", layers.sectors);
    setVis("sectors-line", layers.sectors);
    setVis("cells-dot", layers.cells);
    setVis("cells-label", layers.cells);
    setVis("event-pulse", layers.agentActivity || layers.anomalies);
    if (m.getLayer("event-pulse")) {
      const filterParts: string[] = [];
      if (!layers.agentActivity) filterParts.push("agent_call");
      if (!layers.anomalies) filterParts.push("anomaly");
      const filter: FilterSpecification | undefined = filterParts.length
        ? (["!", ["in", ["get", "kind"], ["literal", filterParts]]] as FilterSpecification)
        : undefined;
      m.setFilter("event-pulse", filter ?? null);
    }
  }, [layers]);

  // Cell-id → centroid lookup for routing events to cells.
  const cellIndex = useMemo(() => {
    const ix = new Map<string, MapCell>();
    for (const c of cells) ix.set(`${c.enodeb_id}/${c.cell_id}`, c);
    // Also index by enodeb_id alone — agent calls don't carry a cell.
    for (const c of cells) if (!ix.has(c.enodeb_id)) ix.set(c.enodeb_id, c);
    return ix;
  }, [cells]);

  // SSE stream + animation loop.
  useEffect(() => {
    if (!cells.length) return;
    const url = `/api/map/events?window=${WINDOW_TO_QUERY[windowKey]}&cap_per_sec=${capPerSec}`;
    const es = new EventSource(url);
    const seenIds = new Set<string>();
    es.onmessage = (ev) => {
      try {
        const e: MapEvent = JSON.parse(ev.data);
        if (e.id && seenIds.has(e.id)) return;
        if (e.id) seenIds.add(e.id);
        eventQueueRef.current.push(e);
      } catch {
        // ignore malformed
      }
    };
    es.onerror = () => {
      // Let it auto-reconnect.
    };

    const tick = () => {
      const now = performance.now();
      const minGap = 1000 / Math.max(0.1, capPerSec);
      // Pulse fade speed: slower → more visible. With 0.015 increment per frame
      // (~60fps), a pulse lives ~1.1s. Bumped from 0.05 (0.33s) for legibility.
      const ageStep = 0.015;
      // Drain at most one event per tick if cap allows.
      if (now - lastDrawAtRef.current >= minGap && eventQueueRef.current.length > 0) {
        const e = eventQueueRef.current.shift()!;
        lastDrawAtRef.current = now;
        // Resolve cell location.
        const key = `${e.enodeb_id ?? ""}/${e.cell_id ?? ""}`;
        const cell = cellIndex.get(key) ?? cellIndex.get(e.enodeb_id ?? "");
        const center = cell ? [cell.lon, cell.lat] : NYC_CENTER;
        setRecentEvents((cur) => [{ ...e }, ...cur].slice(0, 30));
        // Add a pulse feature.
        const m = mapRef.current;
        if (m && m.getSource("events")) {
          const src = m.getSource("events") as maplibregl.GeoJSONSource;
          // Mutate GeoJSON: keep recent ~50 features, age them.
          const cur = (src as unknown as { _data?: { features: any[] } })._data?.features ?? [];
          const aged = cur
            .map((f: any) => ({ ...f, properties: { ...f.properties, age: f.properties.age + ageStep } }))
            .filter((f: any) => f.properties.age < 1);
          aged.unshift({
            type: "Feature",
            geometry: { type: "Point", coordinates: center },
            properties: { kind: e.kind, age: 0 },
          });
          const fc = { type: "FeatureCollection" as const, features: aged.slice(0, 80) };
          (src as unknown as { _data?: typeof fc })._data = fc;
          src.setData(fc);
        }
      } else {
        // Even on idle ticks, age existing pulses so they fade out.
        const m = mapRef.current;
        if (m && m.getSource("events")) {
          const src = m.getSource("events") as maplibregl.GeoJSONSource;
          const cur = (src as unknown as { _data?: { features: any[] } })._data?.features ?? [];
          if (cur.length) {
            const aged2 = cur
              .map((f: any) => ({ ...f, properties: { ...f.properties, age: f.properties.age + ageStep } }))
              .filter((f: any) => f.properties.age < 1);
            const fc = { type: "FeatureCollection" as const, features: aged2 };
            (src as unknown as { _data?: typeof fc })._data = fc;
            src.setData(fc);
          }
        }
      }
      rafRef.current = window.requestAnimationFrame(tick);
    };
    const rafRef = { current: 0 } as { current: number };
    rafRef.current = window.requestAnimationFrame(tick);

    return () => {
      es.close();
      window.cancelAnimationFrame(rafRef.current);
      eventQueueRef.current = [];
    };
  }, [cells.length, cellIndex, windowKey, capPerSec]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 h-[calc(100vh-110px)]">
      <div className="relative rounded-lg border border-slate-200 overflow-hidden bg-white">
        <div ref={containerRef} className="absolute inset-0" />
      </div>
      <aside className="bg-white rounded-lg border border-slate-200 p-3 overflow-auto">
        <h2 className="text-sm font-semibold text-slate-700 mb-2">Network controls</h2>

        <h3 className="text-[11px] uppercase tracking-wide text-slate-500 mt-2 mb-1">Layers</h3>
        <LayerToggle label="Cell sites" value={layers.cells} onChange={(v) => setLayers((l) => ({ ...l, cells: v }))} />
        <LayerToggle label="Sectors (coverage)" value={layers.sectors} onChange={(v) => setLayers((l) => ({ ...l, sectors: v }))} />
        <LayerToggle label="KPI heatmap" value={layers.heatmap} onChange={(v) => setLayers((l) => ({ ...l, heatmap: v }))} disabled />
        <LayerToggle label="Anomaly pulses" value={layers.anomalies} onChange={(v) => setLayers((l) => ({ ...l, anomalies: v }))} />
        <LayerToggle label="Agent activity" value={layers.agentActivity} onChange={(v) => setLayers((l) => ({ ...l, agentActivity: v }))} />

        <h3 className="text-[11px] uppercase tracking-wide text-slate-500 mt-4 mb-1">Throughput cap</h3>
        <div className="flex items-center gap-2">
          <input
            type="range"
            min={0.5}
            max={20}
            step={0.5}
            value={capPerSec}
            onChange={(e) => setCapPerSec(parseFloat(e.target.value))}
            className="flex-1"
          />
          <span className="text-xs tabular-nums text-slate-600 w-14 text-right">{capPerSec.toFixed(1)}/s</span>
        </div>

        <h3 className="text-[11px] uppercase tracking-wide text-slate-500 mt-4 mb-1">Time window</h3>
        <div className="flex flex-wrap gap-1">
          {WINDOW_OPTIONS.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setWindowKey(w)}
              className={clsx(
                "text-xs px-2 py-1 rounded border",
                windowKey === w ? "bg-ink text-white border-ink" : "bg-white border-slate-300 text-slate-700 hover:bg-slate-50",
              )}
            >
              {w}
            </button>
          ))}
        </div>

        <h3 className="text-[11px] uppercase tracking-wide text-slate-500 mt-4 mb-1">Recent events ({recentEvents.length})</h3>
        <ul className="text-xs space-y-1 max-h-72 overflow-auto">
          {recentEvents.map((e, i) => (
            <li
              key={`${e.id}-${i}`}
              className="flex items-center gap-1.5 border-b border-slate-100 py-1 last:border-0 truncate"
              title={`${e.ts} ${e.kind} ${e.enodeb_id ?? ""}/${e.cell_id ?? ""} ${e.kpi ?? ""}${e.magnitude !== null && e.magnitude !== undefined ? `=${e.magnitude}` : ""} ${e.latency_ms ?? ""}`}
            >
              <span
                className={clsx(
                  "inline-block w-1.5 h-1.5 rounded-full shrink-0",
                  e.kind === "anomaly" && "bg-rose-600",
                  e.kind === "agent_call" && "bg-sky-500",
                  e.kind === "incident" && "bg-amber-500",
                )}
              />
              <span className="text-slate-500 tabular-nums shrink-0">{e.ts?.slice(11, 19) ?? "?"}</span>
              <span className="font-mono text-slate-800 shrink-0">
                {e.kind === "agent_call" ? "agent" : e.kind}
              </span>
              {e.enodeb_id && (
                <span className="text-slate-500 shrink-0">
                  {e.enodeb_id}/{e.cell_id ?? "?"}
                </span>
              )}
              {e.latency_ms !== null && e.latency_ms !== undefined && (
                <span className="text-slate-500 ml-auto tabular-nums shrink-0">{e.latency_ms}ms</span>
              )}
              {e.kpi && (
                <span className="text-slate-500 truncate">{e.kpi}={e.magnitude}</span>
              )}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function LayerToggle({ label, value, onChange, disabled }: { label: string; value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className={clsx("flex items-center gap-2 text-sm py-0.5", disabled && "opacity-50")}>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      {label}
      {disabled && <span className="text-[10px] text-slate-400">(soon)</span>}
    </label>
  );
}

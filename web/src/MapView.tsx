import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { RiskClass } from "./api";
import { RISK_COLORS } from "./format";

const BASEMAP = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

interface Props {
  provinces: GeoJSON.FeatureCollection | null;
  classes: Record<string, RiskClass>; // province -> risk class to colour by
  selected: string | null;
  onSelect: (province: string) => void;
}

export function MapView({ provinces, classes, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Create the map once.
  useEffect(() => {
    if (!container.current) return;
    const m = new maplibregl.Map({ container: container.current, style: BASEMAP, center: [100.9, 13.2], zoom: 4.6 });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("provinces", { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "province" });
      m.addLayer({ id: "fill", type: "fill", source: "provinces",
        paint: { "fill-color": ["coalesce", ["get", "color"], "#dddddd"], "fill-opacity": 0.8 } });
      m.addLayer({ id: "outline", type: "line", source: "provinces",
        paint: { "line-color": "#ffffff", "line-width": 0.6 } });
      m.addLayer({ id: "selected", type: "line", source: "provinces", filter: ["==", ["get", "province"], ""],
        paint: { "line-color": "#111111", "line-width": 2.2 } });
      m.on("click", "fill", (e) => {
        const name = e.features?.[0]?.properties?.province;
        if (name) onSelectRef.current(name);
      });
      m.on("mouseenter", "fill", () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", "fill", () => (m.getCanvas().style.cursor = ""));
      ready.current = true;
      m.fire("data-ready");
    });
    map.current = m;
    return () => m.remove();
  }, []);

  // Push data and colours whenever they change.
  useEffect(() => {
    const m = map.current;
    if (!m || !provinces) return;
    const apply = () => {
      const colored: GeoJSON.FeatureCollection = {
        ...provinces,
        features: provinces.features.map((f) => {
          const cls = classes[f.properties?.province as string];
          return { ...f, properties: { ...f.properties, color: cls ? RISK_COLORS[cls] : null } };
        }),
      };
      (m.getSource("provinces") as GeoJSONSource).setData(colored);
    };
    if (ready.current) apply();
    else m.once("data-ready", apply);
  }, [provinces, classes]);

  // Fit the view to the provinces once they arrive, whatever the screen size.
  useEffect(() => {
    const m = map.current;
    if (!m || !provinces) return;
    let [minX, minY, maxX, maxY] = [180, 90, -180, -90];
    const visit = (c: unknown): void => {
      if (typeof (c as number[])[0] === "number") {
        const [x, y] = c as number[];
        minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
      } else (c as unknown[]).forEach(visit);
    };
    provinces.features.forEach((f) => f.geometry && "coordinates" in f.geometry && visit(f.geometry.coordinates));
    m.fitBounds([[minX, minY], [maxX, maxY]], { padding: 20, duration: 0 });
  }, [provinces]);

  useEffect(() => {
    const m = map.current;
    if (m && ready.current) m.setFilter("selected", ["==", ["get", "province"], selected ?? ""]);
  }, [selected]);

  return (
    <div
      ref={container}
      className="map"
      role="img"
      aria-label="Map of Thailand's provinces coloured by flood-exposure risk class. The table lists the same values."
    />
  );
}

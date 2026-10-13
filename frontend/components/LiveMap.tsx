"use client";

import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import type { LiveLocation } from "@/lib/types";

const colors = { ALLOW: "#34d399", REQUEST_2FA: "#fbbf24", HOLD_FOR_REVIEW: "#fb923c", BLOCK: "#fb7185" };

export default function LiveMap({ locations }: { locations: LiveLocation[] }) {
  const center: [number, number] = locations.length ? [locations[0].lat, locations[0].lon] : [20.59, 78.96];
  return <div className="live-map"><MapContainer center={center} zoom={locations.length ? 3 : 2} scrollWheelZoom={false} className="map"><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />{locations.map(location => <CircleMarker key={`${location.txn_id}-${location.lat}-${location.lon}`} center={[location.lat, location.lon]} radius={7} pathOptions={{ color: colors[location.action], fillColor: colors[location.action], fillOpacity: .75 }}><Popup>txn {location.txn_id} · {location.action}<br />{location.city}, {location.country}</Popup></CircleMarker>)}</MapContainer>{!locations.length && <span className="map-empty">No flagged coordinates yet</span>}</div>;
}

"use client";
import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";

export default function MapPanel({ points }: { points: { lat: number; lon: number; label?: string }[] }) {
  const center: [number, number] = points.length ? [points[0].lat, points[0].lon] : [20.59, 78.96];
  return <div className="map-wrap"><MapContainer center={center} zoom={points.length ? 3 : 4} scrollWheelZoom={false} className="map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />{points.map((point, index) => <CircleMarker key={`${point.lat}-${point.lon}-${index}`} center={[point.lat, point.lon]} radius={6} pathOptions={{ color: "#22c55e", fillColor: "#22c55e", fillOpacity: .7 }}><Popup>{point.label ?? "Transaction location"}</Popup></CircleMarker>)}</MapContainer></div>;
}

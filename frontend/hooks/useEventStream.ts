"use client";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import type { StreamEvent } from "@/lib/types";

export function useEventStream() {
  const [event, setEvent] = useState<StreamEvent | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let source: EventSource | null = null;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      source = new EventSource(`${API_URL}/stream`);
      source.onopen = () => setConnected(true);
      source.onmessage = message => { try { setEvent(JSON.parse(message.data) as StreamEvent); } catch { /* ignore malformed events */ } };
      source.onerror = () => { setConnected(false); source?.close(); window.setTimeout(connect, 1500); };
    };
    connect();
    return () => { stopped = true; source?.close(); setConnected(false); };
  }, []);
  return { event, connected };
}

"use client";
import { useEffect, useState } from "react";

export function usePolling<T>(loader: () => Promise<T>, interval = 2000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const run = () => loader().then(value => active && (setData(value), setError(null))).catch(errorValue => active && setError(errorValue instanceof Error ? errorValue.message : "Request failed"));
    run();
    const timer = window.setInterval(run, interval);
    return () => { active = false; window.clearInterval(timer); };
  }, [loader, interval]);
  return { data, error, loading: data === null && error === null };
}

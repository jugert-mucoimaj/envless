"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

export interface ChangeNotice {
  environment_id: string;
  version: string;
  reason: string;
  at: string;
  keys?: string[];
}

/*
  Holds a connection to the backend's activity stream so the panel reflects a
  change the moment it lands - whether it came from this browser, another
  operator, or the API directly. EventSource reconnects on its own, so the only
  work here is reporting whether the line is currently up.
*/
export function useLiveChanges(onChange: (notice: ChangeNotice) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onChange);

  // Kept current in an effect so the stream below never has to be torn down
  // and rebuilt just because the callback identity changed.
  useEffect(() => {
    handler.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/api/activity/stream`);

    source.addEventListener("ready", () => setConnected(true));
    source.addEventListener("change", (event) => {
      try {
        handler.current(JSON.parse((event as MessageEvent).data) as ChangeNotice);
      } catch {
        /* a malformed frame is not worth breaking the panel over */
      }
    });
    source.onerror = () => setConnected(false);
    source.onopen = () => setConnected(true);

    return () => source.close();
  }, []);

  return connected;
}

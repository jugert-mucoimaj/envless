"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Consumer, Environment } from "@/lib/types";

/*
  Who is actually reading this environment, from where, and whether they have
  the current value yet. After a rotation this is the screen that answers the
  only question that matters: is the old value still in use anywhere?
*/

interface Props {
  environment: Environment;
  version: string | null;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

function ago(when: string | null): string {
  if (!when) return "never";
  const seconds = Math.max(0, (Date.now() - new Date(when).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return new Date(when).toLocaleDateString();
}

export default function ConsumersPanel({ environment, version, onError, onNotice }: Props) {
  const [consumers, setConsumers] = useState<Consumer[] | null>(null);

  const load = useCallback(async () => {
    try {
      setConsumers(await api.consumers(environment.id));
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not read the consumer list.");
    }
  }, [environment.id, onError]);

  useEffect(() => {
    void (async () => {
      await load();
    })();
    const tick = setInterval(() => void load(), 4000);
    return () => clearInterval(tick);
  }, [load]);

  async function revoke(consumer: Consumer) {
    try {
      await api.revokeToken(environment.id, consumer.id);
      onNotice(`Revoked ${consumer.name}. It stops reading now.`);
      await load();
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not revoke that token.");
    }
  }

  if (consumers === null) {
    return <p className="label" style={{ margin: 0 }}>Reading…</p>;
  }

  const live = consumers.filter((consumer) => consumer.reading_now);
  const behind = live.filter((consumer) => !consumer.up_to_date);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ margin: 0, color: "var(--ink-soft)", maxWidth: "62ch" }}>
        {live.length === 0
          ? `Nothing has read ${environment.name} in the last ten minutes.`
          : behind.length === 0
            ? `All ${live.length} running on the current value.`
            : `${behind.length} of ${live.length} still on an older value.`}
      </p>

      {consumers.length === 0 ? (
        <p style={{ margin: 0, color: "var(--ink-faint)" }}>
          No tokens issued here yet. Issue one and an application can read this environment.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {consumers.map((consumer) => (
            <li
              key={consumer.id}
              style={{ padding: "11px 0", borderBottom: "1px solid var(--rule)" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <span
                  className="lamp"
                  data-aspect={
                    !consumer.reading_now
                      ? undefined
                      : consumer.up_to_date
                        ? "clear"
                        : "caution"
                  }
                  data-dim={consumer.reading_now ? undefined : "true"}
                  title={
                    !consumer.reading_now
                      ? "Not reading at the moment"
                      : consumer.up_to_date
                        ? "Running on the current value"
                        : "Still on an older value"
                  }
                />
                <span style={{ fontWeight: 500, flex: 1 }}>{consumer.name}</span>
                <span className="label num">{ago(consumer.last_used_at)}</span>
                <button className="btn btn-quiet btn-danger" onClick={() => revoke(consumer)}>
                  Revoke
                </button>
              </div>

              <div
                className="label"
                style={{ margin: "3px 0 0 17px", display: "flex", gap: 16, flexWrap: "wrap" }}
              >
                <span className="data">{consumer.prefix}…</span>
                <span className="data">{consumer.last_ip || "no address yet"}</span>
                <span>
                  {consumer.pull_count} read{consumer.pull_count === 1 ? "" : "s"}
                </span>
                {consumer.reads_in_a_minute > 0 && (
                  <span>{consumer.reads_in_a_minute}/min now</span>
                )}
                <span
                  style={{
                    color: consumer.up_to_date ? "var(--clear)" : "var(--caution-text)",
                  }}
                >
                  {consumer.last_version
                    ? consumer.up_to_date
                      ? "current"
                      : `on ${consumer.last_version.slice(0, 8)}`
                    : "has not read yet"}
                </span>
              </div>

              {consumer.sightings.length > 1 && (
                <p
                  className="label"
                  style={{ margin: "3px 0 0 17px", color: "var(--caution-text)" }}
                >
                  Has read from {consumer.sightings.length} different addresses:{" "}
                  <span className="data">
                    {consumer.sightings.map((sighting) => sighting.ip).join(", ")}
                  </span>
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {version && (
        <p className="label data" style={{ margin: 0 }}>
          Current version {version.slice(0, 8)}
        </p>
      )}
    </div>
  );
}

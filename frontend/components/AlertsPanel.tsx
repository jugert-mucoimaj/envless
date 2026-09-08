"use client";

import type { ActivityEvent } from "@/lib/types";

/*
  The handful of entries that wanted someone to look at them. There are only
  three kinds, and each says in one sentence what happened and what to do next
  - an alert nobody can act on is just noise with a red border.
*/

const WHAT_TO_DO: Record<string, string> = {
  "token.unfamiliar_source":
    "If you did not move this application, revoke the token and issue a new one.",
  "token.burst":
    "An application reading its own configuration is told when it changes, so it should not need to poll. Check what is holding this token.",
  "token.rate_limited":
    "Reads from this token are being refused until it slows down. Nothing has been served to it in the meantime.",
};

interface Props {
  alerts: ActivityEvent[];
  onOpenConsumers: () => void;
}

export default function AlertsPanel({ alerts, onOpenConsumers }: Props) {
  if (alerts.length === 0) {
    return (
      <div>
        <p style={{ margin: "0 0 4px", fontSize: 16 }}>Nothing has looked wrong.</p>
        <p className="label" style={{ margin: 0, maxWidth: "58ch" }}>
          Two things show up here: a token reading from an address it has not used before,
          and a token reading far more often than an application needs to.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ margin: 0, color: "var(--ink-soft)", maxWidth: "62ch" }}>
        Newest first. These are the only entries flagged for attention — everything else is
        in the activity trail.
      </p>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {alerts.map((alert) => (
          <li
            key={alert.id}
            className="recessed"
            style={{
              padding: "11px 13px",
              marginBottom: 9,
              borderLeft: "3px solid var(--danger)",
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span style={{ flex: 1, fontWeight: 500 }}>{alert.summary}</span>
              <span className="label num" style={{ flex: "none" }}>
                {new Date(alert.created_at).toLocaleString()}
              </span>
            </div>

            {WHAT_TO_DO[alert.action] && (
              <p className="label" style={{ margin: "5px 0 0", maxWidth: "58ch" }}>
                {WHAT_TO_DO[alert.action]}
              </p>
            )}

            {typeof alert.detail.known_addresses === "object" && (
              <p className="label data" style={{ margin: "5px 0 0" }}>
                Previously read from {(alert.detail.known_addresses as string[]).join(", ")}
              </p>
            )}
          </li>
        ))}
      </ul>

      <button className="btn" onClick={onOpenConsumers} style={{ alignSelf: "flex-start" }}>
        Show what is reading this environment
      </button>
    </div>
  );
}

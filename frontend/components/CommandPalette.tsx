"use client";

import { useMemo, useState } from "react";

export interface Command {
  id: string;
  title: string;
  hint?: string;
  group: string;
  run: () => void;
}

/*
  A command centre earns the name by being drivable from the keyboard. Ctrl-K
  opens this; typing filters; Enter runs. Nothing here is unavailable elsewhere
  in the panel - it is a faster route to the same controls.
*/

interface Props {
  commands: Command[];
  onClose: () => void;
}

/** Mounted only while open, so opening it always starts from a clean slate. */
export default function CommandPalette({ commands, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [wanted, setWanted] = useState(0);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) =>
      `${command.group} ${command.title} ${command.hint ?? ""}`.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  // Filtering can shorten the list under the cursor, so the highlighted row is
  // clamped as it is read rather than corrected afterwards.
  const active = Math.min(wanted, Math.max(0, matches.length - 1));

  function choose(index: number) {
    const command = matches[index];
    if (!command) return;
    onClose();
    command.run();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20, 33, 61, 0.38)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "13vh",
        zIndex: 60,
      }}
    >
      <div className="plate" style={{ width: "min(640px, 92vw)", overflow: "hidden", borderColor: "var(--ink)" }}>
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") onClose();
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setWanted(Math.min(active + 1, matches.length - 1));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setWanted(Math.max(active - 1, 0));
            }
            if (event.key === "Enter") {
              event.preventDefault();
              choose(active);
            }
          }}
          placeholder="Jump to an environment, or start a job"
          aria-label="Search commands"
          style={{
            width: "100%",
            padding: "13px 16px",
            border: "none",
            borderBottom: "1px solid var(--rule)",
            background: "var(--white)",
            fontSize: 16,
            outline: "none",
          }}
        />
        <div style={{ maxHeight: "46vh", overflowY: "auto" }}>
          {matches.length === 0 ? (
            <p className="label" style={{ padding: "18px 16px", margin: 0 }}>
              Nothing matches that. Try an environment or variable name.
            </p>
          ) : (
            matches.map((command, index) => (
              <button
                key={command.id}
                onMouseEnter={() => setWanted(index)}
                onClick={() => choose(index)}
                style={{
                  display: "flex",
                  width: "100%",
                  alignItems: "baseline",
                  gap: 10,
                  padding: "8px 16px",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  background: index === active ? "var(--ink)" : "transparent",
                  color: index === active ? "var(--lamp)" : "var(--ink)",
                }}
              >
                <span
                  className="label"
                  style={{
                    width: 92,
                    flex: "none",
                    color: index === active ? "rgba(246,247,244,0.7)" : "var(--ink-faint)",
                  }}
                >
                  {command.group}
                </span>
                <span style={{ flex: 1 }}>{command.title}</span>
                {command.hint && (
                  <span
                    className="label data"
                    style={{ color: index === active ? "rgba(246,247,244,0.7)" : "var(--ink-faint)" }}
                  >
                    {command.hint}
                  </span>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

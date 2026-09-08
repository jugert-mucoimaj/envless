"use client";

import type { Environment } from "@/lib/types";

/*
  The promotion path drawn as a signalling diagram: one running line, a signal
  at each environment, and the selected block illuminated the way an occupied
  track circuit lights on a real panel. It is the one loud thing on the page,
  so everything in it has to mean something - the lamp is the environment's
  aspect, the lit block is where you are, and the count is what is actually
  stored there.
*/

const HEIGHT = 92;
const TRACK_Y = 38;

interface Props {
  environments: Environment[];
  selectedId: string | null;
  flashingId: string | null;
  connectedApps: number;
  onSelect: (environment: Environment) => void;
}

export default function RouteDiagram({
  environments,
  selectedId,
  flashingId,
  connectedApps,
  onSelect,
}: Props) {
  if (environments.length === 0) {
    return (
      <div className="recessed" style={{ padding: "20px 18px" }}>
        <p className="label" style={{ margin: 0 }}>
          This project has no environments yet. Add one to start the line.
        </p>
      </div>
    );
  }

  const count = environments.length;
  const width = 1000;
  const margin = 74;
  const span = count > 1 ? (width - margin * 2) / (count - 1) : 0;
  const positionOf = (index: number) => (count > 1 ? margin + span * index : width / 2);
  const selectedIndex = environments.findIndex((environment) => environment.id === selectedId);
  const blockHalf = count > 1 ? Math.min(span / 2 - 8, 96) : 120;

  return (
    <div className="recessed" style={{ padding: "14px 16px 10px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: 4,
        }}
      >
        <span className="label">Promotion line</span>
        <span className="label num">
          {connectedApps === 0
            ? "No apps connected"
            : `${connectedApps} app${connectedApps === 1 ? "" : "s"} connected`}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="group"
        aria-label="Environments on the promotion line"
        style={{ display: "block", overflow: "visible" }}
      >
        {/* The running line. */}
        <line
          x1={margin - 46}
          y1={TRACK_Y}
          x2={width - margin + 46}
          y2={TRACK_Y}
          stroke="var(--ink)"
          strokeWidth={2}
          opacity={0.55}
        />

        {/* The occupied block: where you are looking right now. */}
        {selectedIndex >= 0 && (
          <line
            x1={positionOf(selectedIndex) - blockHalf}
            y1={TRACK_Y}
            x2={positionOf(selectedIndex) + blockHalf}
            y2={TRACK_Y}
            stroke="var(--lamp)"
            strokeWidth={5}
            strokeLinecap="butt"
          />
        )}

        {environments.map((environment, index) => {
          const x = positionOf(index);
          const isSelected = environment.id === selectedId;
          const colour =
            environment.aspect === "danger"
              ? "var(--danger)"
              : environment.aspect === "caution"
                ? "var(--caution)"
                : "var(--clear)";

          return (
            <g
              key={environment.id}
              onClick={() => onSelect(environment)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(environment);
                }
              }}
              tabIndex={0}
              role="button"
              aria-pressed={isSelected}
              aria-label={`${environment.name}, ${environment.variable_count} variables`}
              style={{ cursor: "pointer" }}
            >
              {/* Signal post and head. */}
              <line
                x1={x}
                y1={TRACK_Y}
                x2={x}
                y2={TRACK_Y - 20}
                stroke="var(--ink)"
                strokeWidth={2}
                opacity={0.7}
              />
              <circle
                cx={x}
                cy={TRACK_Y - 26}
                r={8.5}
                fill="var(--ink)"
                opacity={0.85}
              />
              {/* A signal shows its aspect whether or not you are looking at
                  it - that is the point of a panel. Selection brightens it. */}
              <circle
                cx={x}
                cy={TRACK_Y - 26}
                r={5.5}
                fill={colour}
                opacity={isSelected ? 1 : 0.42}
                className={flashingId === environment.id ? "flashing" : undefined}
              />
              {isSelected && (
                <circle cx={x} cy={TRACK_Y - 26} r={11} fill="none" stroke={colour} strokeWidth={1.5} opacity={0.5} />
              )}

              {/* Berth marker on the line itself. */}
              <rect
                x={x - 4}
                y={TRACK_Y - 4}
                width={8}
                height={8}
                fill={isSelected ? "var(--ink)" : "var(--fascia)"}
                stroke="var(--ink)"
                strokeWidth={1.5}
              />

              <text
                x={x}
                y={TRACK_Y + 26}
                textAnchor="middle"
                fill="var(--ink)"
                style={{
                  fontFamily: "var(--font-label)",
                  fontSize: 15,
                  fontWeight: isSelected ? 600 : 400,
                }}
              >
                {environment.name}
              </text>
              <text
                x={x}
                y={TRACK_Y + 43}
                textAnchor="middle"
                fill="var(--ink-soft)"
                style={{
                  fontFamily: "var(--font-label)",
                  fontSize: 12.5,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {environment.variable_count === 1
                  ? "1 variable"
                  : `${environment.variable_count} variables`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

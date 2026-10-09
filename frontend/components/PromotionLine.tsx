"use client";

import type { Environment } from "@/lib/types";

/*
  The environments of a project, in promotion order, drawn on one rule inside
  the band. The rule is the line; each environment is a stop on it; the stop
  you are looking at carries the heavy mark. Each stop also shows its own
  aspect, so production reads as production even while you are on staging.
*/

interface Props {
  environments: Environment[];
  selectedId: string | null;
  flashingId: string | null;
  onSelect: (environment: Environment) => void;
  onAdd: () => void;
}

export default function PromotionLine({
  environments,
  selectedId,
  flashingId,
  onSelect,
  onAdd,
}: Props) {
  return (
    <nav
      aria-label="Environments in promotion order"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.max(environments.length, 1)}, minmax(0, 180px)) auto`,
        columnGap: 18,
        alignItems: "start",
      }}
    >
      {environments.map((environment) => {
        const selected = environment.id === selectedId;
        return (
          <button
            key={environment.id}
            type="button"
            className={`line-stop${flashingId === environment.id ? " flashing" : ""}`}
            aria-pressed={selected}
            onClick={() => onSelect(environment)}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
              {!selected && <span className="mark" data-aspect={environment.aspect} aria-hidden="true" />}
              <span
                className="stop-name"
                style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {environment.name}
              </span>
            </span>
            <span className="stop-count num">
              {environment.variable_count === 1
                ? "1 variable"
                : `${environment.variable_count} variables`}
            </span>
          </button>
        );
      })}
      <button
        type="button"
        className="btn btn-quiet"
        onClick={onAdd}
        style={{ alignSelf: "center", marginTop: 8 }}
        title="Add an environment after the last one"
      >
        Add environment
      </button>
    </nav>
  );
}

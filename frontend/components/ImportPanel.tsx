"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Environment } from "@/lib/types";

/*
  Most environments start life as a .env file someone already has. This is the
  shortest path from that file into envless: paste it, read what will happen,
  and commit.
*/

interface Props {
  environment: Environment;
  onImported: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export default function ImportPanel({ environment, onImported, onError, onNotice }: Props) {
  const [body, setBody] = useState("");
  const [overwrite, setOverwrite] = useState(true);
  const [busy, setBusy] = useState(false);

  const lineCount = body
    .split("\n")
    .filter((line) => line.trim() && !line.trim().startsWith("#") && line.includes("="))
    .length;

  async function run() {
    if (!body.trim()) {
      onError("Paste the contents of a .env file first.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.importVariables(environment.id, body, overwrite);
      onNotice(
        `Added ${result.created}, updated ${result.updated}` +
          (result.skipped ? `, skipped ${result.skipped}` : "") +
          ` in ${environment.name}.`,
      );
      setBody("");
      onImported();
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not read that file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p style={{ margin: 0, color: "var(--ink-soft)", maxWidth: "62ch" }}>
        Paste a .env file. Comments and blank lines are ignored, and{" "}
        <span className="data">export</span> prefixes and quotes are stripped.
      </p>

      <textarea
        className="field data"
        rows={14}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={"DATABASE_URL=postgres://localhost/app\nRATE_LIMIT_PER_MINUTE=60"}
        aria-label="Contents of a .env file"
        spellCheck={false}
        style={{ resize: "vertical", lineHeight: 1.6 }}
      />

      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={overwrite}
          onChange={(event) => setOverwrite(event.target.checked)}
        />
        <span>Replace values that already exist here</span>
      </label>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="btn btn-primary" onClick={run} disabled={busy || lineCount === 0}>
          {busy ? "Importing" : `Import ${lineCount || "0"} variable${lineCount === 1 ? "" : "s"}`}
        </button>
        <span className="label">into {environment.name}</span>
      </div>
    </div>
  );
}

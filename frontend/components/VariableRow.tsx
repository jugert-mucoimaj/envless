"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { generateSecret } from "@/lib/format";
import type { Variable } from "@/lib/types";

/*
  One variable, one row. A row is read-only until you click into it; editing is
  deliberate rather than accidental, because these values are what production
  runs on. Escape abandons the edit, Enter commits it.

  The parent keys each row on the variable's version, so a row that changed
  underneath the operator remounts with fresh state instead of holding a stale
  draft.
*/

interface Props {
  variable: Variable;
  environmentId: string;
  aspect: string;
  flashing: boolean;
  onChanged: (variable: Variable) => void;
  onRemoved: (variableId: string) => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export default function VariableRow({
  variable,
  environmentId,
  aspect,
  flashing,
  onChanged,
  onRemoved,
  onError,
  onNotice,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draftKey, setDraftKey] = useState(variable.key);
  const [draftValue, setDraftValue] = useState("");
  const [shown, setShown] = useState<string | null>(variable.revealed ? variable.value : null);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [rotating, setRotating] = useState(false);

  async function reveal(): Promise<string> {
    if (shown !== null) return shown;
    const full = await api.revealVariable(environmentId, variable.id);
    setShown(full.value);
    return full.value;
  }

  async function beginRotate() {
    // Deliberately does not load the current value. Rotating means replacing
    // it, and showing the compromised one only invites pasting it back.
    setDraftValue("");
    setDraftKey(variable.key);
    setRotating(true);
    setEditing(true);
  }

  async function beginEdit() {
    try {
      setDraftValue(await reveal());
      setDraftKey(variable.key);
      setEditing(true);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not open that value.");
    }
  }

  async function save() {
    const trimmedKey = draftKey.trim();
    if (!trimmedKey) {
      onError("A variable needs a name.");
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateVariable(environmentId, variable.id, {
        key: trimmedKey,
        value: draftValue,
      });
      setShown(updated.value);
      setEditing(false);
      onChanged(updated);
      onNotice(
        rotating
          ? `Rotated ${updated.key}. Anything reading it picks the new value up now.`
          : `Saved ${updated.key}.`,
      );
      setRotating(false);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not save that change.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleSecret() {
    try {
      const updated = await api.updateVariable(environmentId, variable.id, {
        is_secret: !variable.is_secret,
      });
      setShown(updated.value);
      onChanged(updated);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not change that setting.");
    }
  }

  async function remove() {
    try {
      await api.deleteVariable(environmentId, variable.id);
      onRemoved(variable.id);
      onNotice(`Removed ${variable.key}.`);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not remove that variable.");
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(await reveal());
      onNotice(`Copied ${variable.key} to the clipboard.`);
    } catch {
      onError("The browser would not give access to the clipboard.");
    }
  }

  const displayValue = shown ?? variable.value;

  return (
    <div
      className="var-row"
      data-editing={editing || confirmingDelete ? "true" : undefined}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr) 34px 296px",
        gap: 14,
        alignItems: "start",
        padding: "9px 14px",
        borderBottom: "1px solid var(--rule)",
        background: editing ? "var(--plate-lit)" : "transparent",
      }}
    >
      {/* name */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, minHeight: 26 }}>
        {/* An unlit berth lamp until this value moves, then it lights in the
            environment's own aspect. Secrecy is already legible from the
            masked value, so it is not what this reports. */}
        <span
          className={`lamp${flashing ? " flashing" : ""}`}
          data-aspect={flashing ? aspect : undefined}
          aria-hidden="true"
        />
        {editing ? (
          <input
            className="field data"
            value={draftKey}
            onChange={(event) => setDraftKey(event.target.value.toUpperCase())}
            aria-label="Variable name"
            spellCheck={false}
          />
        ) : (
          <button
            type="button"
            onClick={beginEdit}
            className="data"
            style={{
              background: "none",
              border: "none",
              padding: 0,
              textAlign: "left",
              cursor: "pointer",
              fontWeight: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={`Edit ${variable.key}`}
          >
            {variable.key}
          </button>
        )}
      </div>

      {/* value */}
      <div style={{ minWidth: 0 }}>
        {editing ? (
          <textarea
            autoFocus
            className="field data"
            rows={Math.min(6, Math.max(1, draftValue.split("\n").length))}
            value={draftValue}
            onChange={(event) => setDraftValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                setEditing(false);
              }
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void save();
              }
            }}
            aria-label={rotating ? `Replacement for ${variable.key}` : `Value of ${variable.key}`}
            placeholder={rotating ? "Paste the replacement, or generate one" : undefined}
            spellCheck={false}
            style={{ resize: "vertical" }}
          />
        ) : (
          <button
            type="button"
            onClick={beginEdit}
            className="data"
            style={{
              background: "none",
              border: "none",
              padding: "2px 0",
              textAlign: "left",
              cursor: "pointer",
              color: displayValue ? "var(--ink)" : "var(--ink-faint)",
              width: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minHeight: 22,
            }}
            title="Edit this value"
          >
            {displayValue || "empty"}
          </button>
        )}
        {variable.note && !editing && (
          <p className="label" style={{ margin: "2px 0 0" }}>
            {variable.note}
          </p>
        )}
      </div>

      {/* how many times this value has moved - always legible */}
      <span
        className="label num"
        style={{ alignSelf: "center", textAlign: "right" }}
        title="Times this value has changed"
      >
        v{variable.version}
      </span>

      {/* controls */}
      <div
        className="row-actions"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 2,
          minHeight: 26,
        }}
      >
        {editing ? (
          <>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? "Saving" : rotating ? "Replace" : "Save"}
            </button>
            {rotating && (
              <button
                className="btn"
                onClick={() => setDraftValue(generateSecret())}
                title="Fill in a freshly generated value"
              >
                Generate
              </button>
            )}
            <button
              className="btn btn-quiet"
              onClick={() => {
                setEditing(false);
                setRotating(false);
              }}
              disabled={saving}
            >
              Cancel
            </button>
          </>
        ) : confirmingDelete ? (
          <>
            <span className="label">Remove it?</span>
            <button className="btn btn-danger" onClick={remove}>
              Remove
            </button>
            <button className="btn btn-quiet" onClick={() => setConfirmingDelete(false)}>
              Keep
            </button>
          </>
        ) : (
          <>
            {variable.is_secret && (
              <button
                className="btn btn-quiet"
                onClick={() => (shown === null ? void reveal() : setShown(null))}
                title={shown === null ? "Show this value" : "Hide this value"}
              >
                {shown === null ? "Show" : "Hide"}
              </button>
            )}
            <button className="btn btn-quiet" onClick={copy} title="Copy the value">
              Copy
            </button>
            <button
              className="btn btn-quiet"
              onClick={toggleSecret}
              title={
                variable.is_secret
                  ? "Show this value in full from now on"
                  : "Keep this value masked from now on"
              }
            >
              {variable.is_secret ? "Mark plain" : "Mark secret"}
            </button>
            {variable.is_secret && (
              <button
                className="btn btn-quiet"
                onClick={beginRotate}
                title={`Replace ${variable.key} with a new value`}
              >
                Rotate
              </button>
            )}
            <button
              className="btn btn-quiet btn-danger"
              onClick={() => setConfirmingDelete(true)}
              title={`Remove ${variable.key}`}
            >
              Remove
            </button>
          </>
        )}
      </div>
    </div>
  );
}

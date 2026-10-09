"use client";

import { useEffect, type ReactNode } from "react";

/*
  Secondary work - issuing a token, pasting a .env, reading history - happens
  in a drawer over the panel rather than on another screen, so the operator
  never loses sight of which environment they are working in.
*/

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}

export default function Drawer({ open, title, subtitle, onClose, children }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20, 33, 61, 0.38)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 50,
      }}
    >
      <aside
        className="sheet"
        style={{
          width: "min(540px, 94vw)",
          height: "100%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            padding: "18px 24px 14px",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: "-0.015em" }}>
              {title}
            </h2>
            {subtitle && (
              <p style={{ margin: "2px 0 0", color: "var(--ink-2)" }}>
                {subtitle}
              </p>
            )}
          </div>
          <button className="btn btn-quiet" onClick={onClose} aria-label="Close">
            Close
          </button>
        </header>
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 24px 28px" }}>{children}</div>
      </aside>
    </div>
  );
}

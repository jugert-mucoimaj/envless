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
        background: "rgba(25, 28, 24, 0.42)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 50,
      }}
    >
      <aside
        className="plate"
        style={{
          width: "min(520px, 94vw)",
          height: "100%",
          borderRadius: 0,
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
            padding: "14px 18px",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em" }}>
              {title}
            </h2>
            {subtitle && (
              <p className="label" style={{ margin: "1px 0 0" }}>
                {subtitle}
              </p>
            )}
          </div>
          <button className="btn btn-quiet" onClick={onClose} aria-label="Close">
            Close
          </button>
        </header>
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px 24px" }}>{children}</div>
      </aside>
    </div>
  );
}

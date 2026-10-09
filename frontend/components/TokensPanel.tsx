"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AccessToken, Environment } from "@/lib/types";

/*
  Tokens are the join between envless and the things that run on it. The
  plaintext exists for exactly one render - after that the database holds only
  a hash - so the screen has to say that plainly at the moment it matters.
*/

interface Props {
  environment: Environment;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export default function TokensPanel({ environment, onError, onNotice }: Props) {
  const [tokens, setTokens] = useState<AccessToken[]>([]);
  const [name, setName] = useState("");
  const [issued, setIssued] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listTokens(environment.id)
      .then(setTokens)
      .catch((error) => onError(error instanceof ApiError ? error.message : "Could not load tokens."));
  }, [environment.id, onError]);

  async function issue() {
    if (!name.trim()) {
      onError("Give the token a name so you can tell later what is using it.");
      return;
    }
    setBusy(true);
    try {
      const token = await api.issueToken(environment.id, name.trim());
      setIssued(token.token);
      setTokens((current) => [token, ...current]);
      setName("");
      onNotice(`Issued a token for ${environment.name}.`);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not issue that token.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(token: AccessToken) {
    try {
      await api.revokeToken(environment.id, token.id);
      setTokens((current) => current.filter((item) => item.id !== token.id));
      onNotice(`Revoked ${token.name}. Anything using it stops reading now.`);
    } catch (error) {
      onError(error instanceof ApiError ? error.message : "Could not revoke that token.");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <p style={{ margin: 0, color: "var(--ink-soft)", maxWidth: "62ch" }}>
        An application presents one of these to read {environment.name}. It never sees any other
        environment.
      </p>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="field"
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && issue()}
          placeholder="What will use it? e.g. Pigeon web"
          aria-label="Token name"
        />
        <button className="btn btn-primary" onClick={issue} disabled={busy}>
          Issue token
        </button>
      </div>

      {issued && (
        <div
          className="recessed"
          style={{ padding: 12, borderLeft: "3px solid var(--caution-deep)" }}
        >
          <p className="label" style={{ margin: "0 0 6px" }}>
            Copy this now. It is not shown again.
          </p>
          <p
            className="data"
            style={{ margin: "0 0 8px", wordBreak: "break-all", lineHeight: 1.5 }}
          >
            {issued}
          </p>
          <button
            className="btn"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(issued);
                onNotice("Token copied to the clipboard.");
              } catch {
                onError("The browser would not give access to the clipboard.");
              }
            }}
          >
            Copy token
          </button>
        </div>
      )}

      <div>
        <p className="label" style={{ margin: "0 0 6px" }}>
          Issued for this environment
        </p>
        {tokens.length === 0 ? (
          <p style={{ margin: 0, color: "var(--ink-faint)" }}>
            Nothing is reading {environment.name} yet.
          </p>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {tokens.map((token) => (
              <li
                key={token.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  padding: "9px 0",
                  borderBottom: "1px solid var(--rule)",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontWeight: 500 }}>{token.name}</p>
                  <p className="label" style={{ margin: "2px 0 0", display: "flex", gap: 14, flexWrap: "wrap" }}>
                    <span className="data">{token.prefix}…</span>
                    <span>
                      {token.pull_count === 0
                        ? "never used"
                        : `${token.pull_count} pull${token.pull_count === 1 ? "" : "s"}`}
                    </span>
                    {token.last_used_at && <span>last {new Date(token.last_used_at).toLocaleString()}</span>}
                  </p>
                </div>
                <button className="btn btn-quiet btn-danger" onClick={() => revoke(token)}>
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

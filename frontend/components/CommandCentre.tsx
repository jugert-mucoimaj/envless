"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ActivityEvent, EnvironmentStatus, Project, Variable } from "@/lib/types";
import { asDotenvLine, rehide } from "@/lib/format";
import { useLiveChanges, type ChangeNotice } from "@/hooks/useLiveChanges";
import AlertsPanel from "./AlertsPanel";
import CommandPalette, { type Command } from "./CommandPalette";
import Drawer from "./Drawer";
import ConsumersPanel from "./ConsumersPanel";
import ImportPanel from "./ImportPanel";
import RouteDiagram from "./RouteDiagram";
import TokensPanel from "./TokensPanel";
import VariableRow from "./VariableRow";

type DrawerName = "tokens" | "import" | "history" | "consumers" | "alerts" | null;

const ASPECT_LABEL: Record<string, string> = {
  clear: "Safe to change",
  caution: "Change with care",
  danger: "Live traffic",
};

export default function CommandCentre() {
  const [projects, setProjects] = useState<Project[]>([]);
  // What the operator last picked. What is actually shown is derived from it
  // below, so a project or environment disappearing underneath them falls back
  // to something real instead of leaving the panel blank.
  const [pickedProject, setPickedProject] = useState<string | null>(null);
  const [pickedEnvironment, setPickedEnvironment] = useState<string | null>(null);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [status, setStatus] = useState<EnvironmentStatus | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [alerts, setAlerts] = useState<ActivityEvent[]>([]);
  const [database, setDatabase] = useState<string>("checking");

  const [filter, setFilter] = useState("");
  const [drawer, setDrawer] = useState<DrawerName>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Which environment the rows on screen actually belong to. Comparing it
  // with the selected environment is what tells us a read is still in flight.
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ text: string; tone: "ok" | "bad" } | null>(null);
  const [flashing, setFlashing] = useState<string | null>(null);
  const [flashingEnv, setFlashingEnv] = useState<string | null>(null);

  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newSecret, setNewSecret] = useState(true);
  const filterRef = useRef<HTMLInputElement>(null);

  const project = projects.find((item) => item.id === pickedProject) ?? projects[0] ?? null;
  const projectId = project?.id ?? null;
  const environments = useMemo(() => project?.environments ?? [], [project]);
  const environment =
    environments.find((item) => item.id === pickedEnvironment) ?? environments[0] ?? null;
  const environmentId = environment?.id ?? null;

  const say = useCallback((text: string) => setNotice({ text, tone: "ok" }), []);
  const complain = useCallback((text: string) => setNotice({ text, tone: "bad" }), []);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 4200);
    return () => clearTimeout(timer);
  }, [notice]);

  // --- loading ----------------------------------------------------------

  const loadProjects = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not load projects.");
    }
  }, [complain]);

  const loadVariables = useCallback(
    async (id: string) => {
      try {
        const [rows, reading] = await Promise.all([
          api.listVariables(id),
          api.environmentStatus(id),
        ]);
        setVariables(rows);
        setStatus(reading);
        setLoadedFor(id);
      } catch (error) {
        complain(error instanceof ApiError ? error.message : "Could not load this environment.");
      }
    },
    [complain],
  );

  const loadActivity = useCallback(async () => {
    try {
      const [recent, flagged] = await Promise.all([api.activity(40), api.alerts(40)]);
      setActivity(recent);
      setAlerts(flagged);
    } catch {
      /* the ticker is not worth an error message */
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await Promise.all([loadProjects(), loadActivity()]);
      try {
        setDatabase((await api.health()).database);
      } catch {
        setDatabase("unreachable");
      }
    })();
  }, [loadProjects, loadActivity]);

  useEffect(() => {
    if (!environmentId) return;
    void (async () => {
      await loadVariables(environmentId);
    })();
  }, [environmentId, loadVariables]);

  // --- the live line ----------------------------------------------------

  const onLiveChange = useCallback(
    (change: ChangeNotice) => {
      void loadActivity();
      void loadProjects();
      setFlashingEnv(change.environment_id);
      setTimeout(() => setFlashingEnv(null), 1400);
      if (change.environment_id === environmentId) void loadVariables(change.environment_id);
    },
    [environmentId, loadActivity, loadProjects, loadVariables],
  );

  const live = useLiveChanges(onLiveChange);

  // Apps connect, read and fall behind without writing anything, and alerts
  // come from reads. None of that reaches the change stream, so it is polled.
  useEffect(() => {
    if (!environmentId) return;
    const tick = setInterval(() => {
      api.environmentStatus(environmentId).then(setStatus).catch(() => undefined);
      api.alerts(40).then(setAlerts).catch(() => undefined);
    }, 4000);
    return () => clearInterval(tick);
  }, [environmentId]);

  // --- actions ----------------------------------------------------------

  async function addVariable() {
    if (!environmentId) return;
    const key = newKey.trim().toUpperCase();
    if (!key) {
      complain("Give the variable a name.");
      return;
    }
    try {
      const created = await api.createVariable(environmentId, {
        key,
        value: newValue,
        is_secret: newSecret,
      });
      setVariables((current) =>
        [...current, rehide(created)].sort((a, b) => a.key.localeCompare(b.key)),
      );
      setNewKey("");
      setNewValue("");
      setAdding(false);
      say(`Saved ${created.key}.`);
      void loadProjects();
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not save that variable.");
    }
  }

  async function copyAsDotenv() {
    if (!environmentId || !environment) return;
    try {
      const revealed = await api.listVariables(environmentId, true);
      const text = revealed.map(({ key, value }) => asDotenvLine(key, value)).join("\n");
      await navigator.clipboard.writeText(text + "\n");
      say(`Copied ${revealed.length} variables from ${environment.name}.`);
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not copy that environment.");
    }
  }

  async function addProject() {
    const name = window.prompt("What is the project called?");
    if (!name?.trim()) return;
    const slug = name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    try {
      const created = await api.createProject({ name: name.trim(), slug });
      await loadProjects();
      setPickedProject(created.id);
      setPickedEnvironment(created.environments[0]?.id ?? null);
      say(`Created ${created.name} with three environments.`);
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not create that project.");
    }
  }

  async function addEnvironment() {
    if (!project) return;
    const name = window.prompt("What is the environment called?");
    if (!name?.trim()) return;
    const slug = name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    try {
      const created = await api.createEnvironment(project.id, {
        name: name.trim(),
        slug,
        aspect: "clear",
        rank: project.environments.length,
      });
      await loadProjects();
      setPickedEnvironment(created.id);
      say(`Added ${created.name} to ${project.name}.`);
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not add that environment.");
    }
  }

  async function setAspect(next: string) {
    if (!environment) return;
    try {
      await api.updateEnvironment(environment.id, { aspect: next });
      await loadProjects();
      say(`${environment.name} is now marked "${ASPECT_LABEL[next]}".`);
    } catch (error) {
      complain(error instanceof ApiError ? error.message : "Could not change that setting.");
    }
  }

  // --- keyboard ---------------------------------------------------------

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "/" && document.activeElement === document.body) {
        event.preventDefault();
        filterRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = [];
    for (const item of projects) {
      for (const env of item.environments) {
        list.push({
          id: `go-${env.id}`,
          group: "Go to",
          title: `${item.name} · ${env.name}`,
          hint: `${env.variable_count} vars`,
          run: () => {
            setPickedProject(item.id);
            setPickedEnvironment(env.id);
          },
        });
      }
    }
    if (environment) {
      list.push(
        {
          id: "add-variable",
          group: "In here",
          title: "Add a variable",
          run: () => setAdding(true),
        },
        { id: "import", group: "In here", title: "Import a .env file", run: () => setDrawer("import") },
        { id: "tokens", group: "In here", title: "Manage access tokens", run: () => setDrawer("tokens") },
        { id: "history", group: "In here", title: "Show recent changes", run: () => setDrawer("history") },
        { id: "consumers", group: "In here", title: "Show what is reading this environment", run: () => setDrawer("consumers") },
        { id: "alerts", group: "In here", title: "Show alerts", run: () => setDrawer("alerts") },
        { id: "copy", group: "In here", title: "Copy everything as .env", run: () => void copyAsDotenv() },
        {
          id: "download",
          group: "In here",
          title: "Download as .env",
          run: () => window.open(api.exportUrl(environment.id, "dotenv"), "_blank"),
        },
      );
    }
    list.push(
      { id: "new-project", group: "Create", title: "New project", run: () => void addProject() },
      { id: "new-env", group: "Create", title: "New environment", run: () => void addEnvironment() },
    );
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects, environment]);

  const loadingVariables = loadedFor !== environmentId;

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return variables;
    return variables.filter((variable) => variable.key.toLowerCase().includes(needle));
  }, [variables, filter]);

  const aspectColour =
    environment?.aspect === "danger"
      ? "var(--danger)"
      : environment?.aspect === "caution"
        ? "var(--caution)"
        : "var(--clear)";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* ---- status rail ---- */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "0 16px",
          height: 46,
          background: "var(--ink)",
          color: "var(--lamp)",
          flex: "none",
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 17, letterSpacing: "-0.015em" }}>envless</span>
        <span
          className="label"
          style={{ color: "rgba(246,244,236,0.55)", borderLeft: "1px solid rgba(246,244,236,0.25)", paddingLeft: 16 }}
        >
          Configuration control
        </span>

        <div style={{ flex: 1 }} />

        <button
          className="btn btn-quiet"
          onClick={() => setPaletteOpen(true)}
          style={{ color: "rgba(246,244,236,0.75)" }}
        >
          Search and commands
          <span className="data" style={{ opacity: 0.6 }}>
            Ctrl K
          </span>
        </button>

        <button
          className="btn btn-quiet"
          onClick={() => setDrawer("alerts")}
          style={{ color: alerts.length ? "var(--lamp)" : "rgba(246,244,236,0.75)" }}
          title={
            alerts.length
              ? `${alerts.length} thing${alerts.length === 1 ? "" : "s"} worth looking at`
              : "Nothing has looked wrong"
          }
        >
          <span
            className="lamp"
            data-aspect={alerts.length ? "danger" : undefined}
            data-dim={alerts.length ? undefined : "true"}
          />
          {alerts.length ? `Alerts ${alerts.length}` : "Alerts"}
        </button>

        <span style={{ display: "flex", alignItems: "center", gap: 7 }} title={`Database: ${database}`}>
          <span
            className="lamp"
            data-aspect={database === "connected" ? "clear" : undefined}
            data-dim={database === "connected" ? undefined : "true"}
          />
          <span className="label" style={{ color: "rgba(246,244,236,0.7)" }}>
            Database
          </span>
        </span>
        <span
          style={{ display: "flex", alignItems: "center", gap: 7 }}
          title={live ? "Receiving changes as they happen" : "Not receiving live changes"}
        >
          <span className="lamp" data-aspect={live ? "clear" : undefined} data-dim={live ? undefined : "true"} />
          <span className="label" style={{ color: "rgba(246,244,236,0.7)" }}>
            Live
          </span>
        </span>
      </header>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* ---- project rail ---- */}
        <nav
          style={{
            width: "var(--rail-width)",
            flex: "none",
            borderRight: "1px solid var(--edge-dark)",
            background: "var(--fascia-deep)",
            overflowY: "auto",
            padding: "14px 0",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px 6px" }}>
            <span className="label">Projects</span>
            <button className="btn btn-quiet" onClick={addProject} title="New project">
              New
            </button>
          </div>

          {projects.length === 0 ? (
            <p className="label" style={{ padding: "8px 12px", margin: 0 }}>
              Nothing here yet. Create a project to hold its environments.
            </p>
          ) : (
            projects.map((item) => (
              <div key={item.id}>
                <button
                  onClick={() => setPickedProject(item.id)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "6px 12px",
                    border: "none",
                    borderLeft: `3px solid ${item.id === projectId ? "var(--ink)" : "transparent"}`,
                    background: item.id === projectId ? "var(--plate)" : "transparent",
                    cursor: "pointer",
                    fontWeight: item.id === projectId ? 600 : 400,
                  }}
                >
                  {item.name}
                </button>

                {item.id === projectId && (
                  <ul style={{ listStyle: "none", margin: "2px 0 8px", padding: 0 }}>
                    {item.environments.map((env) => (
                      <li key={env.id}>
                        <button
                          onClick={() => setPickedEnvironment(env.id)}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            width: "100%",
                            textAlign: "left",
                            padding: "4px 12px 4px 22px",
                            border: "none",
                            background:
                              env.id === environmentId ? "var(--plate-lit)" : "transparent",
                            cursor: "pointer",
                          }}
                        >
                          <span
                            className={`lamp${flashingEnv === env.id ? " flashing" : ""}`}
                            data-aspect={env.aspect}
                            data-dim={env.id === environmentId ? undefined : "true"}
                          />
                          <span style={{ flex: 1, fontWeight: env.id === environmentId ? 500 : 400 }}>
                            {env.name}
                          </span>
                          <span className="label num">{env.variable_count}</span>
                        </button>
                      </li>
                    ))}
                    <li>
                      <button
                        className="btn btn-quiet"
                        onClick={addEnvironment}
                        style={{ margin: "3px 0 0 19px" }}
                      >
                        Add environment
                      </button>
                    </li>
                  </ul>
                )}
              </div>
            ))
          )}
        </nav>

        {/* ---- panel ---- */}
        <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "14px 16px 0", flex: "none" }}>
            <RouteDiagram
              environments={environments}
              selectedId={environmentId}
              flashingId={flashingEnv}
              connectedApps={status?.connected_apps ?? 0}
              onSelect={(env) => setPickedEnvironment(env.id)}
            />
          </div>

          {environment ? (
            <>
              {/* toolbar */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexWrap: "wrap",
                  padding: "12px 16px 10px",
                  flex: "none",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 8, marginRight: 4 }}>
                  <span className="lamp" data-aspect={environment.aspect} />
                  <span style={{ fontSize: 17, letterSpacing: "-0.01em" }}>
                    <span style={{ color: "var(--ink-soft)", fontWeight: 400 }}>
                      {project?.name}{" "}
                    </span>
                    <span style={{ fontWeight: 600 }}>{environment.name}</span>
                  </span>
                </span>

                <select
                  value={environment.aspect}
                  onChange={(event) => setAspect(event.target.value)}
                  className="label"
                  aria-label="How careful should changes here be"
                  style={{
                    background: "var(--plate)",
                    border: "1px solid var(--recess)",
                    borderRadius: "var(--radius)",
                    padding: "3px 6px",
                    color: aspectColour,
                    cursor: "pointer",
                  }}
                >
                  <option value="clear">Safe to change</option>
                  <option value="caution">Change with care</option>
                  <option value="danger">Live traffic</option>
                </select>

                <div style={{ flex: 1 }} />

                <input
                  ref={filterRef}
                  className="field"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Filter by name"
                  aria-label="Filter variables by name"
                  style={{ width: 190 }}
                />
                <button className="btn" onClick={() => setDrawer("import")}>
                  Import
                </button>
                <button className="btn" onClick={copyAsDotenv}>
                  Copy .env
                </button>
                <button className="btn" onClick={() => setDrawer("consumers")}>
                  Reading
                  {status && status.consumers > 0 ? ` ${status.consumers}` : ""}
                </button>
                <button className="btn" onClick={() => setDrawer("tokens")}>
                  Tokens
                </button>
                <button className="btn" onClick={() => setDrawer("history")}>
                  History
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => setAdding(true)}
                >
                  Add variable
                </button>
              </div>

              {/* Who is running on this, and whether they have the current
                  value. After a change this is where it lands. */}
              {status && status.consumers > 0 && (
                <div
                  className="recessed"
                  style={{
                    margin: "0 16px 10px",
                    padding: "6px 12px",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    flex: "none",
                    borderLeft: `3px solid ${
                      status.waiting.length ? "var(--caution)" : "var(--clear)"
                    }`,
                  }}
                >
                  <span
                    className="lamp"
                    data-aspect={status.waiting.length ? "caution" : "clear"}
                  />
                  <span className="label" style={{ color: "var(--ink)" }}>
                    {status.waiting.length === 0
                      ? `${status.up_to_date} of ${status.consumers} running on the current value`
                      : `${status.up_to_date} of ${status.consumers} on the current value — waiting on ${status.waiting.join(", ")}`}
                  </span>
                  <button
                    className="btn btn-quiet"
                    onClick={() => setDrawer("consumers")}
                    style={{ marginLeft: "auto" }}
                  >
                    Show them
                  </button>
                </div>
              )}

              {/* variable table */}
              <div style={{ flex: 1, minHeight: 0, padding: "0 16px 14px" }}>
                <div
                  className="plate"
                  style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr) 34px 296px",
                      gap: 14,
                      padding: "7px 14px",
                      borderBottom: "1px solid var(--edge-dark)",
                      background: "var(--fascia)",
                      flex: "none",
                    }}
                  >
                    <span className="label">Name</span>
                    <span className="label">Value</span>
                    <span className="label num" style={{ textAlign: "right" }}>
                      Ver
                    </span>
                    <span className="label num" style={{ display: "flex", gap: 18, justifyContent: "flex-end" }}>
                      <span>
                        {shown.length} of {variables.length}
                      </span>
                      {status && <span>version {status.version.slice(0, 8)}</span>}
                    </span>
                  </div>

                  <div style={{ flex: 1, overflowY: "auto" }}>
                    {adding && (
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr) 34px 296px",
                          gap: 14,
                          padding: "9px 14px",
                          borderBottom: "1px solid var(--rule)",
                          background: "var(--plate-lit)",
                          alignItems: "center",
                        }}
                      >
                        <input
                          autoFocus
                          className="field data"
                          value={newKey}
                          onChange={(event) => setNewKey(event.target.value.toUpperCase())}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") setAdding(false);
                            if (event.key === "Enter") void addVariable();
                          }}
                          placeholder="DATABASE_URL"
                          aria-label="New variable name"
                          spellCheck={false}
                        />
                        <input
                          className="field data"
                          value={newValue}
                          onChange={(event) => setNewValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") setAdding(false);
                            if (event.key === "Enter") void addVariable();
                          }}
                          placeholder="postgres://localhost/app"
                          aria-label="New variable value"
                          spellCheck={false}
                        />
                        <span />
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <label className="label" style={{ display: "flex", gap: 5, cursor: "pointer" }}>
                            <input
                              type="checkbox"
                              checked={newSecret}
                              onChange={(event) => setNewSecret(event.target.checked)}
                            />
                            Secret
                          </label>
                          <button className="btn btn-primary" onClick={addVariable}>
                            Save
                          </button>
                          <button className="btn btn-quiet" onClick={() => setAdding(false)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {loadingVariables ? (
                      <p className="label" style={{ padding: "18px 14px", margin: 0 }}>
                        Reading {environment.name}…
                      </p>
                    ) : shown.length === 0 ? (
                      <div style={{ padding: "26px 14px", maxWidth: "56ch" }}>
                        <p style={{ margin: "0 0 4px", fontSize: 16 }}>
                          {variables.length === 0
                            ? `${environment.name} has no variables yet.`
                            : `No variable here matches “${filter}”.`}
                        </p>
                        <p className="label" style={{ margin: "0 0 12px" }}>
                          {variables.length === 0
                            ? "Add them one at a time, or paste a .env file you already have."
                            : "Clear the filter to see the rest."}
                        </p>
                        {variables.length === 0 && (
                          <div style={{ display: "flex", gap: 8 }}>
                            <button className="btn btn-primary" onClick={() => setAdding(true)}>
                              Add a variable
                            </button>
                            <button className="btn" onClick={() => setDrawer("import")}>
                              Import a .env file
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      shown.map((variable) => (
                        <VariableRow
                          key={`${variable.id}:${variable.version}:${variable.is_secret}`}
                          variable={variable}
                          environmentId={environment.id}
                          aspect={environment.aspect}
                          flashing={flashing === variable.key}
                          onChanged={(updated) => {
                            setVariables((current) =>
                              current
                                .map((item) => (item.id === updated.id ? rehide(updated) : item))
                                .sort((a, b) => a.key.localeCompare(b.key)),
                            );
                            setFlashing(updated.key);
                            setTimeout(() => setFlashing(null), 1400);
                          }}
                          onRemoved={(id) => {
                            setVariables((current) => current.filter((item) => item.id !== id));
                            void loadProjects();
                          }}
                          onError={complain}
                          onNotice={say}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div style={{ padding: "40px 16px", maxWidth: "56ch" }}>
              <p style={{ fontSize: 18, margin: "0 0 4px" }}>Pick an environment to see what it holds.</p>
              <p className="label" style={{ margin: 0 }}>
                Every project keeps its own line of environments on the left.
              </p>
            </div>
          )}
        </main>
      </div>

      {/* ---- activity ticker ---- */}
      <footer
        style={{
          flex: "none",
          height: 30,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 16px",
          background: "var(--fascia-deep)",
          borderTop: "1px solid var(--edge-dark)",
          overflow: "hidden",
        }}
      >
        <span className="label" style={{ flex: "none" }}>
          Activity
        </span>
        <span
          className="label num"
          style={{
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: "var(--ink)",
          }}
        >
          {activity.length === 0
            ? "Nothing has happened yet."
            : activity
                .slice(0, 4)
                .map(
                  (event) =>
                    `${new Date(event.created_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}  ${event.summary}`,
                )
                .join("   ·   ")}
        </span>
      </footer>

      {/* ---- transient message ---- */}
      {notice && (
        <div
          role="status"
          className="plate"
          style={{
            position: "fixed",
            bottom: 44,
            left: "50%",
            transform: "translateX(-50%)",
            padding: "8px 14px",
            borderLeft: `3px solid ${notice.tone === "bad" ? "var(--danger)" : "var(--clear)"}`,
            zIndex: 70,
            maxWidth: "min(70ch, 90vw)",
          }}
        >
          {notice.text}
        </div>
      )}

      {paletteOpen && (
        <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />
      )}

      <Drawer
        open={drawer === "tokens"}
        title="Access tokens"
        subtitle={environment ? `${project?.name} · ${environment.name}` : undefined}
        onClose={() => setDrawer(null)}
      >
        {environment && <TokensPanel environment={environment} onError={complain} onNotice={say} />}
      </Drawer>

      <Drawer
        open={drawer === "import"}
        title="Import a .env file"
        subtitle={environment ? `into ${project?.name} · ${environment.name}` : undefined}
        onClose={() => setDrawer(null)}
      >
        {environment && (
          <ImportPanel
            environment={environment}
            onImported={() => {
              void loadVariables(environment.id);
              void loadProjects();
              setDrawer(null);
            }}
            onError={complain}
            onNotice={say}
          />
        )}
      </Drawer>

      <Drawer
        open={drawer === "consumers"}
        title="Reading this environment"
        subtitle={environment ? `${project?.name} · ${environment.name}` : undefined}
        onClose={() => setDrawer(null)}
      >
        {environment && (
          <ConsumersPanel
            environment={environment}
            version={status?.version ?? null}
            onError={complain}
            onNotice={(message) => {
              say(message);
              void loadProjects();
            }}
          />
        )}
      </Drawer>

      <Drawer
        open={drawer === "alerts"}
        title="Alerts"
        subtitle={alerts.length ? `${alerts.length} flagged` : "nothing flagged"}
        onClose={() => setDrawer(null)}
      >
        <AlertsPanel alerts={alerts} onOpenConsumers={() => setDrawer("consumers")} />
      </Drawer>

      <Drawer
        open={drawer === "history"}
        title="Recent changes"
        subtitle={environment ? `${project?.name} · ${environment.name}` : undefined}
        onClose={() => setDrawer(null)}
      >
        {environment && <History environmentId={environment.id} />}
      </Drawer>
    </div>
  );
}

function History({ environmentId }: { environmentId: string }) {
  const [rows, setRows] = useState<{ id: string; key: string; action: string; actor: string; version: number; created_at: string }[]>([]);

  useEffect(() => {
    api.history(environmentId).then(setRows).catch(() => setRows([]));
  }, [environmentId]);

  if (rows.length === 0) {
    return <p style={{ margin: 0, color: "var(--ink-faint)" }}>Nothing has changed here yet.</p>;
  }

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {rows.map((row) => (
        <li
          key={row.id}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 10,
            padding: "7px 0",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <span className="label num" style={{ width: 132, flex: "none" }}>
            {new Date(row.created_at).toLocaleString()}
          </span>
          <span className="data" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {row.key}
          </span>
          <span className="label">
            {row.action} · v{row.version} · {row.actor}
          </span>
        </li>
      ))}
    </ul>
  );
}

# envless command centre

The screen where a name and a value go in and get saved. Next.js App Router,
talking to the backend at `NEXT_PUBLIC_ENVLESS_API`.

```powershell
npm install
copy .env.example .env.local
npm run dev          # http://localhost:3000
```

The backend must be up on port 8000, or the panel says so and does nothing else.

In a container:

```powershell
docker build -t envless-centre --build-arg NEXT_PUBLIC_ENVLESS_API=http://127.0.0.1:8000 ./frontend
docker run --rm -p 3000:3000 envless-centre
```

`NEXT_PUBLIC_ENVLESS_API` is read by the browser, not by the container, so it
is compiled into the client bundle at **build** time. It has to be an address
the browser can reach — the published host port, never a compose service name
— and changing it means rebuilding the image. `output: "standalone"` in
`next.config.ts` is what keeps the runtime image free of `node_modules` and the
build toolchain.

## The design

A control room where the room itself tells you where you are. Every
environment carries an aspect - **clear**, **caution** or **danger** - which is
a real column in the database, not decoration, and it paints the band across
the top of the screen.

- **The band** is the one loud thing on the page. It takes the environment's
  aspect colour and carries the environment's name large enough that nobody
  edits production by accident: green with pale text when it is safe to change,
  true amber with dark ink when it wants care, red when live traffic runs on
  it. Under the name, one sentence says what is running on this environment and
  whether it has the current value yet.
- **The promotion line** runs along the top edge of the band: the project's
  environments in order, each a stop, the one you are looking at carrying the
  heavy mark. A stop you are not on still shows its own aspect.
- **Everything under the band is quiet.** Pale paper, blue-black ink, thin
  rules. No cards, no bevels, no shadows. Projects live in the top bar, so the
  table has the whole width.
- **A value that just moved** from somewhere else is tinted in the
  environment's colour for a moment, then settles. That is the only motion the
  page makes on its own.
- **Colour**: paper `#F6F7F4`, ink `#14213D`, and the three aspects
  `#1E6B57` / `#E2A72E` / `#B23A2B`.
- **Type**: Martian Mono for everything that is literally a machine-readable
  name or value - keys, values, versions, and set wide for the environment's
  name. Schibsted Grotesk for the sentences and the controls.

Row controls stay hidden until a row is hovered or focused. Seventeen rows each
repeating "Copy, Mark secret, Remove" is noise; the controls remain in the
document and reachable by keyboard.

## The files

| | |
|---|---|
| `app/globals.css` | the whole design system: tokens, plates, lamps, controls |
| `components/CommandCentre.tsx` | the shell — selection, loading, live updates, actions |
| `components/PromotionLine.tsx` | the promotion line along the band |
| `components/VariableRow.tsx` | one variable: read, reveal, edit, rename, remove |
| `components/CommandPalette.tsx` | Ctrl-K — jump to an environment or start a job |
| `components/TokensPanel.tsx` | issuing and revoking what applications read with |
| `components/ConsumersPanel.tsx` | what is reading this environment, from where, on which version |
| `components/AlertsPanel.tsx` | the few entries flagged for attention, and what to do about each |
| `components/ImportPanel.tsx` | pasting a .env file in |
| `components/Drawer.tsx` | the over-panel the side panels above open in |
| `hooks/useLiveChanges.ts` | the connection that keeps the panel current |
| `lib/api.ts` | every call to the backend, with readable errors |

## Rotating

**Rotate** on a secret row opens the editor with the value blank. That is
deliberate — rotating means replacing the value, and showing the compromised
one only invites pasting it back. **Generate** fills in a fresh one for
credentials envless itself mints.

Above the table, a strip says how many running applications are on the current
value and names any that are not. It comes from the environment's status, which
the panel polls, so it settles on its own as each one catches up.

The **Alerts** lamp in the top bar lights when a token reads from an unfamiliar
address or reads far more often than an application should.

## Getting around

- **Ctrl-K** opens the command palette.
- **/** focuses the filter.
- **Enter** in a row saves, **Escape** abandons the edit.

## Notes

- Selection is derived, not synchronised: the panel keeps what you last picked
  and falls back to something real if it disappears, so an environment deleted
  elsewhere never leaves a blank screen.
- Writes return the value in full — you just typed it — and the panel puts a
  secret back behind its mask before storing it in the list.
- `allowedDevOrigins` in `next.config.ts` covers both `localhost` and
  `127.0.0.1`. Without it, Next blocks its own dev resources on whichever one
  it did not start under and the page never hydrates.
